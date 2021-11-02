"""
References:
https://github.com/mdietrichstein/tensorflow-open_nsfw
https://github.com/yahoo/open_nsfw
"""

from typing import Dict, Tuple

import numpy as np
import tensorflow as tf
from tensorflow.keras import layers

WEIGHTS: Dict[str, Dict[str, np.ndarray]] = np.load(
    "../weights/open_nsfw-weights.npy", encoding="latin1", allow_pickle=True
).item()


def _get_weights(layer_name: str, field_name: str) -> np.ndarray:
    if layer_name not in WEIGHTS:
        raise ValueError(f"No weights found for layer {layer_name}.")

    w = WEIGHTS[layer_name]
    if field_name not in w:
        raise ValueError(f"No field {field_name} in layer {layer_name}.")

    return w[field_name].astype(np.float32)


def _fully_connected(name: str, units: int) -> layers.Dense:
    return layers.Dense(
        name=name,
        units=units,
        kernel_initializer=tf.constant_initializer(
            _get_weights(name, "weights")
        ),
        bias_initializer=tf.constant_initializer(
            _get_weights(name, "biases")
        )
    )


def _conv2d(
        name: str,
        num_filters: int,
        kernel_size: int,
        stride: int,
        padding: str = "same"
) -> layers.Conv2D:
    return layers.Conv2D(
        name=name,
        filters=num_filters,
        kernel_size=kernel_size,
        strides=stride,
        padding=padding,
        kernel_initializer=tf.constant_initializer(
            _get_weights(name, "weights")
        ),
        bias_initializer=tf.constant_initializer(
            _get_weights(name, "biases")
        )
    )


def _batch_norm(name: str) -> layers.BatchNormalization:
    return layers.BatchNormalization(
        name=name,
        epsilon=1e-05,  # Default used in Caffe.
        gamma_initializer=tf.constant_initializer(
            _get_weights(name, "scale")
        ),
        beta_initializer=tf.constant_initializer(
            _get_weights(name, "offset")
        ),
        moving_mean_initializer=tf.constant_initializer(
            _get_weights(name, "mean")
        ),
        moving_variance_initializer=tf.constant_initializer(
            _get_weights(name, "variance")
        ),
    )


def _conv_block(
        stage: int,
        block: int,
        inputs: tf.Tensor,
        nums_filters: Tuple[int, int, int],
        kernel_size: int = 3,
        stride: int = 2,
) -> tf.Tensor:
    num_filters_1, num_filters_2, num_filters_3 = nums_filters

    conv_name_base = f"conv_stage{stage}_block{block}_branch"
    bn_name_base = f"bn_stage{stage}_block{block}_branch"
    shortcut_name_post = f"_stage{stage}_block{block}_proj_shortcut"

    shortcut = _conv2d(
        name=f"conv{shortcut_name_post}",
        num_filters=num_filters_3,
        kernel_size=1,
        stride=stride,
        padding="same"
    )(inputs)

    shortcut = _batch_norm(f"bn{shortcut_name_post}")(shortcut)

    x = _conv2d(
        name=f"{conv_name_base}2a",
        num_filters=num_filters_1,
        kernel_size=1,
        stride=stride,
        padding="same"
    )(inputs)
    x = _batch_norm(f"{bn_name_base}2a")(x)
    x = tf.nn.relu(x)

    x = _conv2d(
        name=f"{conv_name_base}2b",
        num_filters=num_filters_2,
        kernel_size=kernel_size,
        stride=1,
        padding="same"
    )(x)
    x = _batch_norm(f"{bn_name_base}2b")(x)
    x = tf.nn.relu(x)

    x = _conv2d(
        name=f"{conv_name_base}2c",
        num_filters=num_filters_3,
        kernel_size=1,
        stride=1,
        padding="same"
    )(x)
    x = _batch_norm(f"{bn_name_base}2c")(x)

    x = layers.Add()([x, shortcut])

    return tf.nn.relu(x)


def _identity_block(
        stage: int,
        block: int,
        inputs: tf.Tensor,
        nums_filters: Tuple[int, int, int],
        kernel_size: int
) -> tf.Tensor:
    num_filters_1, num_filters_2, num_filters_3 = nums_filters

    conv_name_base = f"conv_stage{stage}_block{block}_branch"
    bn_name_base = f"bn_stage{stage}_block{block}_branch"

    x = _conv2d(
        name=f"{conv_name_base}2a",
        num_filters=num_filters_1,
        kernel_size=1,
        stride=1,
        padding="same"
    )(inputs)
    x = _batch_norm(f"{bn_name_base}2a")(x)
    x = tf.nn.relu(x)

    x = _conv2d(
        name=f"{conv_name_base}2b",
        num_filters=num_filters_2,
        kernel_size=kernel_size,
        stride=1,
        padding="same"
    )(x)
    x = _batch_norm(f"{bn_name_base}2b")(x)
    x = tf.nn.relu(x)

    x = _conv2d(
        name=f"{conv_name_base}2c",
        num_filters=num_filters_3,
        kernel_size=1,
        stride=1,
        padding="same"
    )(x)
    x = _batch_norm(f"{bn_name_base}2c")(x)

    x = layers.Add()([x, inputs])

    return tf.nn.relu(x)


def make_open_nsfw_model_and_load_weights(
        input_shape: Tuple[int, int, int] = (224, 224, 3)
) -> tf.keras.Model:
    image_input = layers.Input(shape=input_shape, name="input")
    x = image_input

    x = tf.pad(x, [[0, 0], [3, 3], [3, 3], [0, 0]], "CONSTANT")
    x = _conv2d("conv_1", num_filters=64, kernel_size=7, stride=2,
                padding="valid")(x)

    x = _batch_norm("bn_1")(x)
    x = tf.nn.relu(x)

    x = layers.MaxPooling2D(pool_size=3, strides=2, padding="same")(x)

    x = _conv_block(stage=0, block=0, inputs=x,
                    nums_filters=(32, 32, 128),
                    kernel_size=3, stride=1)

    x = _identity_block(stage=0, block=1, inputs=x,
                        nums_filters=(32, 32, 128), kernel_size=3)
    x = _identity_block(stage=0, block=2, inputs=x,
                        nums_filters=(32, 32, 128), kernel_size=3)

    x = _conv_block(stage=1, block=0, inputs=x,
                    nums_filters=(64, 64, 256),
                    kernel_size=3, stride=2)
    x = _identity_block(stage=1, block=1, inputs=x,
                        nums_filters=(64, 64, 256), kernel_size=3)
    x = _identity_block(stage=1, block=2, inputs=x,
                        nums_filters=(64, 64, 256), kernel_size=3)
    x = _identity_block(stage=1, block=3, inputs=x,
                        nums_filters=(64, 64, 256), kernel_size=3)

    x = _conv_block(stage=2, block=0, inputs=x,
                    nums_filters=(128, 128, 512),
                    kernel_size=3, stride=2)
    x = _identity_block(stage=2, block=1, inputs=x,
                        nums_filters=(128, 128, 512), kernel_size=3)
    x = _identity_block(stage=2, block=2, inputs=x,
                        nums_filters=(128, 128, 512), kernel_size=3)
    x = _identity_block(stage=2, block=3, inputs=x,
                        nums_filters=(128, 128, 512), kernel_size=3)
    x = _identity_block(stage=2, block=4, inputs=x,
                        nums_filters=(128, 128, 512), kernel_size=3)
    x = _identity_block(stage=2, block=5, inputs=x,
                        nums_filters=(128, 128, 512), kernel_size=3)

    x = _conv_block(stage=3, block=0, inputs=x,
                    nums_filters=(256, 256, 1024), kernel_size=3,
                    stride=2)
    x = _identity_block(stage=3, block=1, inputs=x,
                        nums_filters=(256, 256, 1024),
                        kernel_size=3)
    x = _identity_block(stage=3, block=2, inputs=x,
                        nums_filters=(256, 256, 1024),
                        kernel_size=3)

    x = layers.AveragePooling2D(pool_size=7, strides=1,
                                padding="valid", name="pool")(x)

    x = layers.Reshape((-1, 1024))(x)

    logits = _fully_connected(name="fc_nsfw", units=2)(x)
    output = tf.nn.softmax(logits, name="predictions")

    model = tf.keras.Model(image_input, output)
    return model


def main() -> None:
    model = make_open_nsfw_model_and_load_weights()


if __name__ == "__main__":
    main()
