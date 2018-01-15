import tensorflow as tf

class WeightUncertainty(object):
    """
    Implements the 'Weight Uncertainty in Neural Networks' paper Charles Blundell et al.
    http://proceedings.mlr.press/v37/blundell15.pdf
    https://arxiv.org/abs/1505.05424
    """

    def __init__(self, layer_name):
        self.layer_number = layer_name

    @staticmethod
    def _make_positive(x):
            # return tf.log(1. + tf.exp(x))
            # return tf.exp(x)
            return tf.nn.softplus(x)

    @staticmethod
    def _get_random_weight_or_bias(shape, mu_regulariser, tensor_name):
        mu = tf.get_variable(tensor_name + '-mu', initializer=mu_initializer)
        rho = tf.get_variable(tensor_name + '-rho', initializer=tf.constant(0.1))
        sigma = WeightUncertainty._make_positive(rho)
        noise_sample = tf.random_normal(shape)

        weight_or_bias = mu + sigma * noise_sample
        return weight_or_bias

        # f = log q - log pw pdw
        # could possibly put the log(q) term in. Blundell seems to say it's not needed, but the sampled epsilon might?

    def get_weight_regularizer_scale(self):
        return 0.5

    # Note: should only be called once
    def __call__(self, inputs, num_outputs, activation_fn, normalizer_fn=None, normaliser_params=None,
                 weights_initializer=None, weights_regularizer=None, biases_initializer=None, biases_regularizer=None,
                 trainable=True):
        # TODO: sort out normalisers...I don't use them yet.

        #  weights
        weight_shape = [inputs.get_shape()[1].value, num_outputs]
        if weights_initializer is None:
            weights_initializer = tf.truncated_normal(weight_shape, stddev=0.01)
        weights = WeightUncertainty._get_random_weight_or_bias(weight_shape, weights_initializer, self.layer_name + '-weights')
        tf.add_to_collection(tf.GraphKeys.REGULARIZATION_LOSSES, weights_regularizer(weights))

        #  biases
        bias_shape = [num_outputs]
        if biases_initializer is None:
            biases_initializer = tf.constant(0.0, shape=bias_shape)
        biases = WeightUncertainty._get_random_weight_or_bias(bias_shape, biases_initializer, self.layer_name + '-biases')
        tf.add_to_collection(tf.GraphKeys.REGULARIZATION_LOSSES, biases_regularizer(biases))

        fc_layer_out = activation_fn(tf.matmul(inputs, weights) + biases)
        return fc_layer_out
