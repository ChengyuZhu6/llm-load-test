import json
import logging
import time
import os

import requests
import urllib3

from plugins import plugin, utils
from result import RequestResult

from transformers import LlamaTokenizer

urllib3.disable_warnings()
"""
Example plugin config.yaml:

plugin: "torch_serve_plugin"
plugin_options:
  streaming: True/False
  host: "http://127.0.0.1"
  model_name: "llama"
  endpoint: "/v1/models/llm"
  api: "predict"
  custom_headers: {"Host": "llmtorch-predictor.default.svc.cluster.local"}
  proxies: {}
"""

required_args = ["host", "streaming", "endpoint", "api", "custom_headers"]

logger = logging.getLogger("user")

# This plugin is written primarily for testing torchserve.
class TorchServePlugin(plugin.Plugin):
    def __init__(self, args):
        self._parse_args(args)

    def _parse_args(self, args):
        for arg in required_args:
            if arg not in args:
                logger.error("Missing plugin arg: %s", arg)

        if args["streaming"]:
            self.request_func = self.streaming_request_http
        else:
            self.request_func = self.request_http

        self.model_name = args.get("model_name")
        self.api = args.get("api")
        self.host = args.get("host") + args.get("endpoint")  + ":" + self.api
        if args.get("custom_headers"):
            self.custome_headers = {}
            for key,value in args.get("custom_headers").items():
                self.custome_headers[key] = value
        else:
            self.custome_headers = None

        self.timeout_sec = args.get("timeout_sec")
        self.model_path = args.get("model_path")
        self.tokenizer = LlamaTokenizer.from_pretrained(self.model_path, trust_remote_code=True)
        
        utils.set_proxy(args.get("proxies"))

    def request_http(self, query: dict, user_id: int, test_end_time: float = 0):

        result = RequestResult(user_id, query.get("text"), query.get("input_tokens"))

        result.start_time = time.time()

        headers = {"Content-Type": "application/json"}
        if self.custome_headers != None:
            for key,value in self.custome_headers.items():
                headers[key] = value

        data = {
             "instances": [
                {
                    "text": query["text"],
                    "max_tokens": query["output_tokens"],
                    "min_tokens": query["output_tokens"],
                    "temperature": 1.0,
                    "top_p": 0.9,
                    "seed": 10,
                }
             ]
        }
        prompt_token_ids = self.tokenizer(query["text"]).input_ids
        prompt_len = len(prompt_token_ids)
        response = None
        try:
            response = requests.post(self.host, headers=headers, json=data, verify=False)
            response.raise_for_status()
        except requests.exceptions.ConnectionError as err:
            result.end_time = time.time()
            result.error_text = repr(err)
            if response is not None:
                result.error_code = response.status_code
            logger.exception("Connection error")
            return result
        except requests.exceptions.HTTPError as err:
            result.end_time = time.time()
            result.error_text = repr(err)
            if response is not None:
                result.error_code = response.status_code
            logger.exception("HTTP error")
            return result

        result.end_time = time.time()

        logger.debug("Response: %s", json.dumps(response.text))

        try:
            message = json.loads(response.text)
            error = message.get("error")
            print(message)
            if error is None:
                result.output_text = message["Output"]
                result.output_tokens = message["Output_tokens"]
                result.input_tokens = prompt_len
            else:
                result.error_code = response.status_code
                result.error_text = error
                logger.error("Error received in response message: %s", error)
        except json.JSONDecodeError:
            logger.exception("Response could not be json decoded: %s", response.text)
            result.error_text = f"Response could not be json decoded {response.text}"
        except KeyError:
            logger.exception("KeyError, unexpected response format: %s", response.text)
            result.error_text = f"KeyError, unexpected response format: {response.text}"

        # For non-streaming requests we are keeping output_tokens_before_timeout and output_tokens same.
        result.output_tokens_before_timeout = result.output_tokens
        result.calculate_results()

        return result


    def streaming_request_http(self, query: dict, user_id: int, test_end_time: float):
        headers = {"Content-Type": "application/json"}

        data = {
                "max_tokens": query["output_tokens"],
                "temperature": 0.1,
                "stream": True,
            }
        if "/v1/chat/completions" in self.host:
            data["messages"] = [
                    {"role": "user", "content": query["text"]}
                ]
        else:
            data["prompt"] = query["text"],
            data["min_tokens"] = query["output_tokens"]

        # some runtimes only serve one model, won't check this.
        if self.model_name is not None:
            data["model"] = self.model_name

        result = RequestResult(user_id, query.get("input_id"), query.get("input_tokens"))

        tokens = []
        response = None
        result.start_time = time.time()
        try:
            response = requests.post(
                self.host, headers=headers, json=data, verify=False, stream=True, timeout=self.timeout_sec
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError as err:
            result.end_time = time.time()
            result.error_text = repr(err)
            if response is not None:
                result.error_code = response.status_code
            logger.exception("Connection error")
            return result
        except requests.exceptions.HTTPError as err:
            result.end_time = time.time()
            result.error_text = repr(err)
            if response is not None:
                result.error_code = response.status_code
            logger.exception("HTTP error")
            return result

        logger.debug("Response: %s", response)
        message = None
        for line in response.iter_lines():
            logger.debug("response line: %s", line)
            _, found, data = line.partition(b"data: ")
            if found and data != b"[DONE]":
                try:
                    message = json.loads(data)
                    logger.debug("Message: %s", message)
                    if "/v1/chat/completions" in self.host and not message["choices"][0]['delta'].get('content'):
                        message["choices"][0]['delta']['content']=""
                    error = message.get("error")
                    if error is None:
                        if "/v1/chat/completions" in self.host:
                            token = message["choices"][0]['delta']['content']
                        else:
                            token = message["choices"][0]["text"]
                        logger.debug("Token: %s", token)
                    else:
                        result.error_code = response.status_code
                        result.error_text = error
                        logger.error("Error received in response message: %s", error)
                        break
                except json.JSONDecodeError:
                    logger.exception("Response line could not be json decoded: %s", line)
                except KeyError:
                    logger.exception(
                        "KeyError, unexpected response format in line: %s", line
                    )
                    continue
            else:
                continue

            try:
                # First chunk may not be a token, just a connection ack
                if not result.ack_time:
                    result.ack_time = time.time()

                # First non empty token is the first token
                if not result.first_token_time and token != "":
                    result.first_token_time = time.time()

                # If the current token time is outside the test duration, record the total tokens received before
                # the current token.
                if (
                    not result.output_tokens_before_timeout
                    and time.time() > test_end_time
                ):
                    result.output_tokens_before_timeout = len(tokens)

                tokens.append(token)

                # Last token comes with finish_reason set.
                if message.get("choices", [])[0].get("finish_reason", None):
                    result.output_tokens = message["usage"]["completion_tokens"]
                    result.input_tokens = message["usage"]["prompt_tokens"]
                    result.stop_reason =  message["choices"][0]["finish_reason"]

                    # If test duration timeout didn't happen before the last token is received, 
                    # total tokens before the timeout will be equal to the total tokens in the response.
                    if not result.output_tokens_before_timeout:
                        result.output_tokens_before_timeout = result.output_tokens

            except KeyError:
                logging.exception("KeyError, unexpected response format in line: %s", line)

        # Full response received, return
        result.end_time = time.time()
        result.output_text = "".join(tokens)

        if not result.input_tokens:
            logger.warning("Input token count not found in response, using dataset input_tokens")
            result.input_tokens = query.get("input_tokens")

        if not result.output_tokens:
            logger.warning("Output token count not found in response, length of token list")
            result.output_tokens = len(tokens)

        result.calculate_results()
        return result
