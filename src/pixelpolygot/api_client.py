import base64
import json
import os
import requests
import openai
from threading import Thread
from PySide6.QtCore import Signal, QObject # Need QObject for signals


class ApiClient(QObject): # Inherit from QObject to use signals
    api_response_ready = Signal(str)
    api_error = Signal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config

    def _read_image_base64(self, file_path):
        """Reads an image file and returns its base64 encoded string."""
        try:
            with open(file_path, "rb") as image_file:
                image_data = image_file.read()
            return base64.b64encode(image_data).decode("utf-8")
        except Exception as e:
            raise IOError(f"Failed to read image file {file_path}: {e}") from e

    def _request_ollama(self, image_base64):
        """Sends a request to the Ollama API and emits signals with the response."""
        api_url = f"{self.config['api_url'].rstrip('/')}/api/chat"
        payload = {
            "model": self.config["model"],
            "messages": [
                {
                    "role": "user",
                    "content": self.config["prompt"],
                    "images": [image_base64],
                }
            ],
            "stream": True,
        }

        try:
            response = requests.post(api_url, json=payload, stream=True, timeout=60) # Increased timeout
            response.raise_for_status()

            full_response = ""
            for line in response.iter_lines():
                if line:
                    try:
                        json_response = json.loads(line)
                        if json_response.get("done", False): # Check for 'done' flag
                            if json_response.get("error"):
                                raise Exception(f"Ollama API Error: {json_response['error']}")
                            break # Exit loop if done and no error
                        if message := json_response.get("message"):
                             if content := message.get("content"):
                                full_response += content
                                self.api_response_ready.emit(full_response) # Emit partial response

                    except json.JSONDecodeError:
                        print(f"Warning: Could not decode JSON line: {line}")
                        continue
                    except Exception as e: # Catch errors within the loop
                         print(f"Error processing Ollama stream chunk: {e}")
                         self.api_error.emit(f"Error processing Ollama stream: {str(e)}")
                         return # Stop processing on error

            if not full_response and not response.content: # Check if response was truly empty
                 self.api_error.emit("No response content received from Ollama.")


        except requests.exceptions.RequestException as e:
            error_message = f"Ollama API Request Error: {str(e)}"
            print(error_message)
            self.api_error.emit(error_message)
        except Exception as e: # Catch other potential errors
            error_message = f"Unexpected error during Ollama request: {str(e)}"
            print(error_message)
            self.api_error.emit(error_message)


    def _request_openai(self, image_base64):
        """Sends a request to an OpenAI-compatible API and emits signals with the response."""
        try:
            client = openai.OpenAI(
                api_key=self.config["api_key"], base_url=self.config["api_url"]
            )

            print(f"Using API URL: {self.config['api_url']}")
            print(f"Using model: {self.config['model']}")

            model_name = self.config["model"].lower()
            is_qwen = "qwen" in model_name
            is_dashscope = "dashscope" in self.config["api_url"].lower()
            # Determine if streaming should be used based on model or API type
            # Example: Assume streaming for Qwen, Omni, or if explicitly configured
            use_streaming = is_qwen or model_name.endswith("-omni-7b")

            # Construct image payload based on API/model specifics
            if is_qwen or is_dashscope:
                image_url_payload = {"url": f"data:image/jpeg;base64,{image_base64}"}
            else:
                # Default OpenAI vision payload
                image_url_payload = {
                    "url": f"data:image/jpeg;base64,{image_base64}",
                    "detail": "high",
                }

            system_message = {
                "role": "system",
                "content": "You are a helpful assistant.",
            }

            user_message = {
                "role": "user",
                "content": [
                    {"type": "text", "text": self.config["prompt"]},
                    {"type": "image_url", "image_url": image_url_payload},
                ],
            }

            messages = [system_message, user_message]

            if use_streaming:
                response = client.chat.completions.create(
                    model=self.config["model"],
                    messages=messages,
                    max_tokens=1500, # Increased max_tokens
                    stream=True,
                    timeout=60, # Increased timeout
                )

                full_response = ""
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_response += content
                        self.api_response_ready.emit(full_response) # Emit partial response

                if not full_response:
                     self.api_error.emit("No response content received from API (streaming).")

            else: # Non-streaming request
                response = client.chat.completions.create(
                    model=self.config["model"],
                    messages=messages,
                    max_tokens=1500,
                    stream=False,
                    timeout=60,
                )
                if response.choices and response.choices[0].message:
                    full_response = response.choices[0].message.content
                    self.api_response_ready.emit(full_response) # Emit full response at once
                else:
                    self.api_error.emit("No response content received from API (non-streaming).")

        except openai.APIConnectionError as e:
            error_message = f"OpenAI API Connection Error: {e}"
            print(error_message)
            self.api_error.emit(error_message)
        except openai.APIStatusError as e:
            error_message = f"OpenAI API Status Error ({e.status_code}): {e.response.text}"
            print(error_message)
            self.api_error.emit(error_message)
        except openai.RateLimitError as e:
             error_message = f"OpenAI Rate Limit Error: {e}"
             print(error_message)
             self.api_error.emit(error_message)
        except Exception as e:
            error_message = f"Unexpected OpenAI API Error: {str(e)}"
            print(error_message)
            self.api_error.emit(error_message)


    def process_image_in_thread(self, file_path):
        """Handles the API request in a separate thread."""
        thread = Thread(target=self._api_request_thread_target, args=(file_path,))
        thread.daemon = True
        thread.start()

    def _api_request_thread_target(self, file_path):
        """Target function for the API request thread."""
        try:
            image_base64 = self._read_image_base64(file_path)
            api_type = self.config.get("api_type", "openai").lower() # Default to openai

            if api_type == "ollama":
                self._request_ollama(image_base64)
            elif api_type == "openai":
                self._request_openai(image_base64)
            else:
                 raise ValueError(f"Unsupported API type: {api_type}")

        except IOError as e: # Catch file reading errors specifically
            error_message = f"File Error: {str(e)}"
            print(error_message)
            self.api_error.emit(error_message)
        except ValueError as e: # Catch invalid API type
             error_message = str(e)
             print(error_message)
             self.api_error.emit(error_message)
        except Exception as e:
            # Generic catch-all for unexpected errors during setup/dispatch
            error_message = f"Error preparing API request: {str(e)}"
            print(error_message)
            self.api_error.emit(error_message)