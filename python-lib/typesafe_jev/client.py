# Copyright 2026 Dataiku SAS
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

"""Client for the TypeSafe System One API: https://docs.typesafe.ai/api"""
from concurrent.futures import ThreadPoolExecutor

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

DEFAULT_BASE_URL = "https://api.typesafe.ai"
RETRYABLE_STATUSES = (429, 500, 502, 503, 504, 529)
MAX_PARALLEL_CALLS = 16


class TypeSafeError(Exception):
    pass


class JevClient:
    """Calls POST /v1/systemone, retrying connection errors, rate limits and server errors with backoff.

    This is the only retry layer. Timeouts are not retried, and failures are not handed to the LLM Mesh to retry
    again, so a hung API costs one timeout.
    """

    def __init__(self, api_key, model, timeout, base_url=DEFAULT_BASE_URL):
        if not api_key:
            raise TypeSafeError("No TypeSafe API key: select a 'TypeSafe API key' preset in the model settings.")
        self.url = base_url.rstrip("/") + "/v1/systemone"
        self.model = model
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["Authorization"] = "Bearer " + api_key
        # Judgments have no side effects, so retrying a POST is safe.
        retry = Retry(total=4, read=0, backoff_factor=1, status_forcelist=RETRYABLE_STATUSES,
                      allowed_methods=frozenset(["POST"]), raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retry, pool_maxsize=MAX_PARALLEL_CALLS)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    @classmethod
    def from_preset(cls, preset, model, timeout):
        return cls(preset.get("api_key"), model, timeout, preset.get("base_url") or DEFAULT_BASE_URL)

    def ask(self, state, questions):
        """TypeSafe's response to one request: {"model", "answers", "usage"}."""
        payload = {"state": state, "model": self.model, "questions": questions}
        try:
            resp = self.session.post(self.url, json=payload, timeout=self.timeout)
        except requests.RequestException as e:
            raise TypeSafeError("TypeSafe API call failed: %s" % e) from e
        if resp.status_code != 200:
            raise TypeSafeError("TypeSafe API returned HTTP %s: %s" % (resp.status_code, resp.text[:1000]))
        try:
            return resp.json()
        except ValueError as e:
            raise TypeSafeError("TypeSafe API returned a response that isn't JSON: %s" % resp.text[:200]) from e

    def ask_each(self, states, questions):
        """Asks the same questions about each state, in parallel; responses in the same order."""
        if not states:
            return []
        with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL_CALLS, len(states))) as pool:
            return list(pool.map(lambda state: self.ask(state, questions), states))

