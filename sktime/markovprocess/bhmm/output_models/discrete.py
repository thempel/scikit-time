
# This file is part of BHMM (Bayesian Hidden Markov Models).
#
# Copyright (c) 2016 Frank Noe (Freie Universitaet Berlin)
# and John D. Chodera (Memorial Sloan-Kettering Cancer Center, New York)
#
# BHMM is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import numpy as np
from numpy.random import dirichlet

from sktime.markovprocess.bhmm.output_models.outputmodel import OutputModel
from ._bhmm_output_models import discrete as discrete


class DiscreteOutputModel(OutputModel):
    r""" HMM output probability model using discrete symbols.

    This is the "standard" HMM that is classically used in the literature.

    Create a 1D Gaussian output model.

    Parameters
    ----------
    B : ndarray((N, M), dtype=float)
        output probability matrix using N hidden states and M observable symbols.
        This matrix needs to be row-stochastic.
    prior : None or broadcastable to ndarray((N, M), dtype=float)
        Prior for the initial distribution of the HMM.
        Currently implements the Dirichlet prior that is conjugate to the
        Dirichlet distribution of :math:`b_i`. :math:`b_i` is sampled from:
        .. math:
            b_i \sim \prod_j b_{ij}_i^{a_{ij} + n_{ij} - 1}
        where :math:`n_{ij}` are the number of times symbol :math:`j` has
        been observed when the hidden trajectory was in state :math:`i`
        and :math:`a_{ij}` is the prior count.
        The default prior=None corresponds to :math:`a_{ij} = 0`.
            This option ensures coincidence between sample mean an MLE.

    Examples
    --------

    Create an observation model.

    >>> import numpy as np
    >>> B = np.array([[0.5, 0.5], [0.1, 0.9]])
    >>> output_model = DiscreteOutputModel(B)

    """
    def __init__(self, B, prior=None, ignore_outliers=False):
        self._output_probabilities = np.array(B)
        n_states, self._nsymbols = self._output_probabilities.shape[0], self._output_probabilities.shape[1]
        # superclass constructor
        super(DiscreteOutputModel, self).__init__(n_states=n_states, ignore_outliers=ignore_outliers)
        # test if row-stochastic
        assert np.allclose(self._output_probabilities.sum(axis=1), np.ones(self.n_states)), 'B is no stochastic matrix'
        # set prior matrix
        if prior is None:
            prior = np.zeros((n_states, self._nsymbols))
        else:
            prior = np.zeros((n_states, self._nsymbols)) + prior  # will fail if not broadcastable
        self.prior = prior

    @property
    def model_type(self):
        r""" Model type. Returns 'discrete' """
        return 'discrete'

    @property
    def output_probabilities(self):
        r""" Row-stochastic (n,m) output probability matrix from n hidden states to m symbols. """
        return self._output_probabilities

    @property
    def nsymbols(self):
        r""" Number of symbols, or observable output states """
        return self._nsymbols

    def sub_output_model(self, states):
        return DiscreteOutputModel(self._output_probabilities[states])

    def p_obs(self, obs, out=None):
        """
        Returns the output probabilities for an entire trajectory and all hidden states

        Parameters
        ----------
        obs : ndarray((T), dtype=int)
            a discrete trajectory of length T

        Return
        ------
        p_o : ndarray (T,N)
            the probability of generating the symbol at time point t from any of the N hidden states

        """
        if out is None:
            out = self._output_probabilities[:, obs].T
            return self._handle_outliers(out)
        else:
            if obs.shape[0] == out.shape[0]:
                np.copyto(out, self._output_probabilities[:, obs].T)
            elif obs.shape[0] < out.shape[0]:
                out[:obs.shape[0], :] = self._output_probabilities[:, obs].T
            else:
                raise ValueError(f'output array out is too small: {len(out)} < {len(obs)}')
            return self._handle_outliers(out)

    def fit(self, observations, weights):
        """
        Maximum likelihood estimation of output model given the observations and weights

        Parameters
        ----------

        observations : [ ndarray(T_k) ] with K elements
            A list of K observation trajectories, each having length T_k
        weights : [ ndarray(T_k, N) ] with K elements
            A list of K weight matrices, each having length T_k and containing the probability of any of the states in
            the given time step

        Examples
        --------

        Generate an observation model and samples from each state.

        >>> import numpy as np
        >>> ntrajectories = 3
        >>> nobs = 1000
        >>> B = np.array([[0.5,0.5],[0.1,0.9]])
        >>> output_model = DiscreteOutputModel(B)

        >>> from scipy import stats
        >>> nobs = 1000
        >>> obs = np.empty(nobs, dtype = object)
        >>> weights = np.empty(nobs, dtype = object)

        >>> gens = [stats.rv_discrete(values=(range(len(B[i])), B[i])) for i in range(B.shape[0])]
        >>> obs = [gens[i].rvs(size=nobs) for i in range(B.shape[0])]
        >>> weights = [np.zeros((nobs, B.shape[1])) for i in range(B.shape[0])]
        >>> for i in range(B.shape[0]): weights[i][:, i] = 1.0

        Update the observation model parameters my a maximum-likelihood fit.

        >>> output_model.fit(obs, weights)

        """
        # initialize output probability matrix
        self._output_probabilities.fill(0)
        # update output probability matrix (numerator)
        for obs, w in zip(observations, weights):
            discrete.update_p_out(obs, w, self._output_probabilities)
        # normalize
        self._output_probabilities /= np.sum(self._output_probabilities, axis=1)[:, None]

    def sample(self, observations_by_state):
        """
        Sample a new set of distribution parameters given a sample of observations from the given state.

        The internal parameters are updated.

        Parameters
        ----------
        observations :  [ numpy.array with shape (N_k,) ] with n_states elements
            observations[k] are all observations associated with hidden state k

        Examples
        --------

        initialize output model

        >>> B = np.array([[0.5, 0.5], [0.1, 0.9]])
        >>> output_model = DiscreteOutputModel(B)

        sample given observation

        >>> obs = [[0, 0, 0, 1, 1, 1], [1, 1, 1, 1, 1, 1]]
        >>> output_model.sample(obs)

        """
        N, M = self._output_probabilities.shape  # n_states, nsymbols
        for i, obs_by_state in enumerate(observations_by_state):
            # count symbols found in data
            count = np.bincount(obs_by_state, minlength=M).astype(float)
            # sample dirichlet distribution
            count += self.prior[i]
            positive = count > 0
            # if counts at all: can't sample, so leave output probabilities as they are.
            self._output_probabilities[i, positive] = dirichlet(count[positive])

    def generate_observation_from_state(self, state_index):
        """
        Generate a single synthetic observation data from a given state.

        Parameters
        ----------
        state_index : int
            Index of the state from which observations are to be generated.

        Returns
        -------
        observation : float
            A single observation from the given state.

        Examples
        --------

        Generate an observation model.

        >>> output_model = DiscreteOutputModel(np.array([[0.5,0.5],[0.1,0.9]]))

        Generate sample from each state.

        >>> observation = output_model.generate_observation_from_state(0)

        """
        # generate random generator (note that this is inefficient - better use one of the next functions
        import scipy.stats
        gen = scipy.stats.rv_discrete(values=(range(len(self._output_probabilities[state_index])),
                                              self._output_probabilities[state_index]))
        gen.rvs(size=1)

    def generate_observations_from_state(self, state_index, nobs):
        """
        Generate synthetic observation data from a given state.

        Parameters
        ----------
        state_index : int
            Index of the state from which observations are to be generated.
        nobs : int
            The number of observations to generate.

        Returns
        -------
        observations : numpy.array of shape(nobs,) with type dtype
            A sample of `nobs` observations from the specified state.

        Examples
        --------

        Generate an observation model.

        >>> output_model = DiscreteOutputModel(np.array([[0.5,0.5],[0.1,0.9]]))

        Generate sample from each state.

        >>> observations = [output_model.generate_observations_from_state(state_index, nobs=100) for state_index in range(output_model.n_states)]

        """
        import scipy.stats
        gen = scipy.stats.rv_discrete(values=(range(self._nsymbols), self._output_probabilities[state_index]))
        gen.rvs(size=nobs)

    def generate_observation_trajectory(self, s_t, dtype=None):
        """
        Generate synthetic observation data from a given state sequence.

        Parameters
        ----------
        s_t : numpy.array with shape (T,) of int type
            s_t[t] is the hidden state sampled at time t

        Returns
        -------
        o_t : numpy.array with shape (T,) of type dtype
            o_t[t] is the observation associated with state s_t[t]
        dtype : numpy.dtype, optional, default=None
            The datatype to return the resulting observations in. If None, will select int32.

        Examples
        --------

        Generate an observation model and synthetic state trajectory.

        >>> nobs = 1000
        >>> output_model = DiscreteOutputModel(np.array([[0.5,0.5],[0.1,0.9]]))
        >>> s_t = np.random.randint(0, output_model.n_states, size=[nobs])

        Generate a synthetic trajectory

        >>> o_t = output_model.generate_observation_trajectory(s_t)

        """
        if dtype is None:
            dtype = np.int32

        # Determine number of samples to generate.
        T = s_t.shape[0]
        nsymbols = self._output_probabilities.shape[1]

        if (s_t.max() >= self.n_states) or (s_t.min() < 0):
            msg = ''
            msg += 's_t = %s\n' % s_t
            msg += 's_t.min() = %d, s_t.max() = %d\n' % (s_t.min(), s_t.max())
            msg += 's_t.argmax = %d\n' % s_t.argmax()
            msg += 'self.n_states = %d\n' % self.n_states
            msg += 's_t is out of bounds.\n'
            raise ValueError(msg)

        o_t = np.zeros([T], dtype=dtype)
        for t in range(T):
            s = s_t[t]
            o_t[t] = np.random.choice(nsymbols, p=self._output_probabilities[s, :])

        return o_t
