# Copyright (c) 2022-2023, NVIDIA CORPORATION.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Mixin used by stages which are emitting newly constructed DataFrame or MessageMeta instances into the segment."""

import logging
from abc import ABC
from collections import OrderedDict

import cupy as cp
import mrc
import numpy as np
import pandas as pd
from mrc.core import operators as ops

import cudf

from morpheus.common import TypeId
from morpheus.common import typeid_to_numpy_str
from morpheus.config import CppConfig
from morpheus.messages import MessageMeta
from morpheus.messages import MultiMessage
from morpheus.utils.type_aliases import DataFrameType
from morpheus.utils.type_utils import pretty_print_type_name

logger = logging.getLogger(__name__)


class PreallocatorMixin(ABC):
    """
    Mixin intented to be added to stages, typically source stages,  which are emitting newly constructed DataFrame or
    MessageMeta instances into the segment. During segment build, if the `_needed_columns` addtribut is not empty an
    additional node will be inserted into the graph after the derived class' node which will perform the allocation.

    The exceptions would be non-source stages like DFP's `DFPFileToDataFrameStage` which are not sources but are
    constructing new Dataframe instances, and `LinearBoundaryIngressStage` which is potentially emitting other message
    types such as MultiMessages and it's various derived messages but it would still be the first stage in the given
    segment emitting the message.
    """

    def set_needed_columns(self, needed_columns: OrderedDict):
        """
        Sets the columns needed to perform preallocation. This should only be called by the Pipeline at build time.
        The needed_columns shoudl contain the entire set of columns needed by any other stage in this segment.
        """
        self._needed_columns = needed_columns

    def _preallocate_df(self, df: DataFrameType) -> DataFrameType:
        missing_columns = [col for col in self._needed_columns.keys() if col not in df.columns]
        if len(missing_columns) > 0:
            if isinstance(df, cudf.DataFrame):
                alloc_func = cp.zeros
            else:
                alloc_func = np.zeros

            num_rows = len(df)
            for column_name in missing_columns:
                column_type = self._needed_columns[column_name]
                logger.debug("Preallocating column %s[%s]", column_name, column_type)
                if column_type != TypeId.STRING:
                    column_type_str = typeid_to_numpy_str(column_type)
                    df[column_name] = alloc_func(num_rows, column_type_str)
                else:
                    df[column_name] = ''

        return df

    def _preallocate_meta(self, msg: MessageMeta) -> MessageMeta:
        with msg.mutable_dataframe() as df:
            self._preallocate_df(df)

        return msg

    def _preallocate_multi(self, msg: MultiMessage) -> MultiMessage:
        self._preallocate_meta(msg.meta)
        return msg

    def _post_build_single(self, builder: mrc.Builder, out_node: mrc.SegmentObject) -> mrc.SegmentObject:
        out_type = self.output_ports[0].output_type
        pretty_type = pretty_print_type_name(out_type)

        if len(self._needed_columns) > 0:
            node_name = f"{self.unique_name}-preallocate"

            if issubclass(out_type, (MessageMeta, MultiMessage)):
                # Intentionally not using `_build_cpp_node` because `LinearBoundaryIngressStage` lacks a C++ impl
                if CppConfig.get_should_use_cpp():
                    import morpheus._lib.stages as _stages
                    needed_columns = list(self._needed_columns.items())
                    if issubclass(out_type, MessageMeta):
                        node = _stages.PreallocateMessageMetaStage(builder, node_name, needed_columns)
                    else:
                        node = _stages.PreallocateMultiMessageStage(builder, node_name, needed_columns)
                else:
                    if issubclass(out_type, MessageMeta):
                        node = builder.make_node(node_name, ops.map(self._preallocate_meta))
                    else:
                        node = builder.make_node(node_name, ops.map(self._preallocate_multi))
            elif issubclass(out_type, (cudf.DataFrame, pd.DataFrame)):
                node = builder.make_node(node_name, ops.map(self._preallocate_df))
            else:
                msg = ("Additional columns were requested to be inserted into the Dataframe, but the output type "
                       f"{pretty_type} isn't a supported type")
                raise RuntimeError(msg)

            builder.make_edge(out_node, node)
            out_node = node

        return out_node
