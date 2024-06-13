# SPDX-FileCopyrightText: Copyright (c) 2023, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import typing

import cupy as cp
import mrc
import pandas as pd
from mrc.core import operators as ops

import cudf

from morpheus.cli.register_stage import register_stage
from morpheus.config import Config
from morpheus.messages import MultiMessage
from morpheus.messages import MultiResponseMessage
from morpheus.messages import ResponseMemory
from morpheus.pipeline.single_port_stage import SinglePortStage
from morpheus.pipeline.stage_schema import StageSchema


@register_stage("unittest-conv-msg", ignore_args=["expected_data"])
class ConvMsg(SinglePortStage):
    """
    Simple test stage to convert a MultiMessage to a MultiResponseProbsMessage
    Basically a cheap replacement for running an inference stage.

    Setting `expected_data` to a DataFrame will cause the probs array to by populated by the values in the DataFrame.
    Setting `expected_data` to `None` causes the probs array to be a copy of the incoming dataframe.
    Setting `columns` restricts the columns copied into probs to just the ones specified.
    Setting `order` specifies probs to be in either column or row major
    Setting `empty_probs` will create an empty probs array with 3 columns, and the same number of rows as the dataframe
    """

    def __init__(self,
                 c: Config,
                 expected_data: typing.Union[pd.DataFrame, cudf.DataFrame] = None,
                 columns: typing.List[str] = None,
                 order: str = 'K',
                 probs_type: str = 'f4',
                 empty_probs: bool = False):
        super().__init__(c)

        if expected_data is not None:
            assert isinstance(expected_data, (pd.DataFrame, cudf.DataFrame))

        self._expected_data = expected_data
        self._columns = columns
        self._order = order
        self._probs_type = probs_type
        self._empty_probs = empty_probs

    @property
    def name(self) -> str:
        return "test"

    def accepted_types(self) -> typing.Tuple:
        return (MultiMessage, )

    def compute_schema(self, schema: StageSchema):
        schema.output_schema.set_type(MultiResponseMessage)

    def supports_cpp_node(self) -> bool:
        return False

    def _conv_message(self, message: MultiMessage) -> MultiResponseMessage:
        if self._expected_data is not None:
            if (isinstance(self._expected_data, cudf.DataFrame)):
                df = self._expected_data.copy(deep=True)
            else:
                df = cudf.DataFrame(self._expected_data)

        else:
            if self._columns is not None:
                df = message.get_meta(self._columns)
            else:
                df = message.get_meta()

        if self._empty_probs:
            probs = cp.zeros([len(df), 3], 'float')
        else:
            probs = cp.array(df.values, dtype=self._probs_type, copy=True, order=self._order)

        memory = ResponseMemory(count=len(probs), tensors={'probs': probs})
        return MultiResponseMessage.from_message(message, memory=memory)

    def _build_single(self, builder: mrc.Builder, input_node: mrc.SegmentObject) -> mrc.SegmentObject:
        node = builder.make_node(self.unique_name, ops.map(self._conv_message))
        builder.make_edge(input_node, node)

        return node
