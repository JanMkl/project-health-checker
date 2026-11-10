# Copyright 2026, Jan Melén
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
"""Project Health Checker agent.

Fetches git logs, issues, and pull requests for a project and asks an AI coding
CLI to produce a management memo summarising project direction, contributors,
and health.
"""

__version__ = "0.2.0"
