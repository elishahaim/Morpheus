# Copyright (c) 2020-2023, NVIDIA CORPORATION.
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


class Dataset():

    def __init__(self, df):
        self._df = df.reset_index(drop=True)
        self._dataset_len = self._df.shape[0]

    @property
    def length(self):
        """
        Returns dataframe length
        """
        return self._dataset_len

    @property
    def data(self):
        """
        Retruns dataframe
        """
        return self._df
