#!/usr/bin/env python
"""
Sairen Cross-Entropy Method example.

The cross entropy method basically guesses random weights, runs with them, and
notes the reward.  After doing that several times, it computes the mean and standard
deviation of the weights with the best rewards, and uses them to generate new weights.
Repeat until satisfied.

CEM is usually only effective for a very small number of parameters (tens or hundreds).

This example uses a simple linear combination of the weights and the observation
as its continuous action.  Runs CEM for 10 iterations of 30 episodes of 100 steps,
outputs stats, and writes best params to params.csv in the current directory.
"""

import datetime
import itertools

import numpy as np

from sairen import MarketEnv
from sairen.xform import BinaryDelta

# 1 iteration runs `EPISODES` episodes, each with different parameters.  Each episode is `STEPS_PER_EPISODE` steps.
ITERATIONS = 2
EPISODES = 10
STEPS_PER_EPISODE = 5


class ContinuousActionLinearPolicy:
    """Agent that multiplies the observation by its weights and returns the sum."""
    def __init__(self, theta, n_in, n_out):
        print('ContinuousActionLinearPolicy - theta:',theta,len(theta),n_in,n_out)
        assert len(theta) == (n_in + 1) * n_out, 'n_in {}, n_out {}, len(theta) {}'.format(n_in, n_out, len(theta))
        self.W = theta[0:n_in * n_out].reshape(n_in, n_out)
        self.b = theta[n_in * n_out:None].reshape(1, n_out)

    def act(self, ob):
        return np.squeeze(np.asarray(ob).dot(self.W) + self.b)


def cem(eval_func, params_mean, batch_size, n_iter, elite_frac, params_std=1.0):
    """
    Cross-entropy method for maximizing a black-box function.

    Returns an iterator of dicts with information on each of `n_iter` iterations, each consisting of `batch_size` episodes.

    :param eval_func: function mapping from params vector to reward; instantiates agent with
      the given params, runs it for an episode, and returns the total reward.  Also takes optional episode number for display.
    :param params_mean: Starting means of agent parameters
    :param batch_size: number of samples of parameters to evaluate per batch
    :param n_iter: number of batches
    :param elite_frac: each batch, select this fraction of the top-performing samples
    :param params_std: initial standard deviation of parameters
    """
    n_elite = int(np.round(batch_size * elite_frac))
    params_std = np.ones_like(params_mean) * params_std

    for _ in range(n_iter):
        print("========================cem:",n_iter,params_mean)
        params = np.array([params_mean + dth for dth in params_std[None, :] * np.random.randn(batch_size, params_mean.size)])
        print("params_mean after :",params)
        rewards = np.array([eval_func(p, ep) for ep, p in enumerate(params)])
        print("rewards:",rewards)
        elite_inds = rewards.argsort()[::-1][:n_elite]
        elite_params = params[elite_inds]
        print("elite_params :",elite_params)
        params_mean = elite_params.mean(axis=0)
        params_std = elite_params.std(axis=0)
        print("params_mean,params_std",params_mean,params_std)
        yield {'params_mean': params, 'rewards': rewards, 'params_best': elite_params[0], 'reward_best': rewards.max(), 'reward_elite': rewards[elite_inds].mean(), 'elite_mean': params_mean, 'elite_std': params_std, 'reward_mean': rewards.mean(), 'reward_std': rewards.std()}


def evaluate(env, agent, steps, iteration=None, episode=None, render=True):
    print("==============================evaluate enter: steps",steps)

    """:Return: the total reward for running `agent` in `env` for `steps`.

    :param int,None steps: Number of steps to run for, or None for infinite.
    :param int iteration: The iteration number, just used for display.
    :param int episode: The episode number, just used for display.
    """
    total_reward = 0
    obs = env.reset()

    for _ in itertools.islice(itertools.count(), steps):     # So None means infinite
        print("==============================evaluate itertools:",_)
        action = np.asscalar(agent.act(obs))
        print("---------------action:",action,obs)
        obs, reward, done, info = env.step(action)
        total_reward += reward
        if render: env.render()
        if done: break

    print('\nIteration {} episode {}: {:.2f}\n'.format(iteration, episode, total_reward))
    return total_reward


import logging

def main():
    #env = MarketEnv("BTC-USD", max_quantity = 10, quantity_increment = 1, obs_type = 'time', obs_size = 10, obs_xform=BinaryDelta(3), episode_steps=STEPS_PER_EPISODE, client_id=2)
    env = MarketEnv("BTC-USD", max_quantity = 10, quantity_increment = 1, obs_type = 'time', obs_size = 30, episode_steps=STEPS_PER_EPISODE, client_id=2, loglevel=logging.DEBUG)

    obs_size = env.observation_space.shape[0]
    print('obs size:',obs_size)

    def evaluate_params(agent_params, iteration=None, episode=None):
        print("++++++++++++++++++++++++++++evaluate_params enter:",agent_params, iteration, episode)
        """Closure passed to `cem()` that just takes `agent_params`, initializes an agent, runs until done,
         and returns the total reward.

         :param int iteration: If given, pass the iteration number to `evaluate`.
         :param int episode: If given, pass the episode number to `evaluate`.
         """
        agent = ContinuousActionLinearPolicy(agent_params, obs_size, n_out=1)
        return evaluate(env, agent, steps=None, iteration=iteration, episode=episode)

    iteration = 0
    init_mean = np.zeros(obs_size + 1)
    init_std  = 1.0
    for stats in cem(lambda params, episode: evaluate_params(params, iteration, episode),
                     init_mean,
                     params_std=init_std,
                     n_iter=ITERATIONS,
                     batch_size=EPISODES,
                     elite_frac=0.2):
        timestamp = datetime.datetime.utcnow().replace(microsecond=0)
        print('\n\nITERATION {:2d} REWARD {:.2f} +/- {:.2f}\n\n'.format(iteration, stats['reward_mean'], stats['reward_std']))
        print(timestamp)
        print('Best reward {:4.2f}'.format(stats['reward_best']))
        print('Best params     : {}'.format(repr(stats['params_best'])))
        print('Top reward  {:4.2f}'.format(stats['reward_elite']))
        print('Top params mean : {}'.format(repr(stats['elite_mean'])))
        print('Top params std  : {}'.format(repr(stats['elite_std'])))
        print('\n' * 50)
        with open('params.csv', 'a') as bestfile:
            print(timestamp, env.instrument.symbol, iteration, stats['reward_elite'], 'mean', ','.join('{:.3f}'.format(s) for s in stats['elite_mean']), sep=',', file=bestfile)
            print(timestamp, env.instrument.symbol, iteration, stats['reward_elite'], 'std',  ','.join('{:.3f}'.format(s) for s in stats['elite_std']),  sep=',', file=bestfile)
        iteration += 1
    print("--------------------------env close--------------------")
    env.close()

if __name__ == "__main__":
    main()
