from models.base_model import BaseLLM
from openai import OpenAI, APIConnectionError, RateLimitError
from typing import Any
import base64
import os
from pathlib import Path
import time
from tqdm import tqdm

from mydatasets.BaseDataset import Figure, PageContent


class ImageLLM(BaseLLM):
    # def __init__(
    #     self,
    #     api_key: str | None = os.getenv("OPENAI_API_KEY"),
    #     model_name: str = "gpt-4o",
    # ):
    #     self.model = OpenAI(api_key=api_key)
    #     self.create_ask_message = lambda question: {
    #         "role": "user",
    #         "content": [
    #             {"type": "text", "text": question},
    #         ],
    #     }
    #     self.create_ans_message = lambda ans: {
    #         "role": "assistant",
    #         "content": [
    #             {"type": "text", "text": ans},
    #         ],
    #     }
    #     self.model_name = model_name
    def __init__(
        self,
        api_key: str | None = os.getenv("DASHSCOPE_API_KEY"),
        model_name: str = "qwen-vl-plus",
    ):
        self.base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.model = OpenAI(api_key=api_key, base_url=self.base_url)
        self.create_ask_message = lambda question: {
            "role": "user",
            "content": [
                {"type": "text", "text": question},
            ],
        }
        self.create_ans_message = lambda ans: {
            "role": "assistant",
            "content": [
                {"type": "text", "text": ans},
            ],
        }
        self.model_name = model_name

    def create_text_message(self, texts, question):
        content = []
        for text in texts:
            content.append({"type": "text", "text": text})
        content.append({"type": "text", "text": question})
        message = {"role": "user", "content": content}
        return message

    def process_message(  # type: ignore
        self, question, texts, images, history, figure_message_contents=[]
    ):
        if history is not None:
            assert self.is_valid_history(history)
            messages = history
        else:
            messages = []
        if texts is not None:
            messages.append(self.create_text_message(texts, question))
        if images is not None:
            messages.append(
                self.create_image_message(
                    images, question, figure_message_contents=figure_message_contents
                )
            )

        if (texts is None or len(texts) == 0) and (images is None or len(images) == 0):
            messages.append(self.create_ask_message(question))

        return messages

    def create_image_message(self, images, question, figure_message_contents=[]):
        if figure_message_contents:
            content = figure_message_contents
            content.append(
                {
                    "type": "text",
                    "text": "The next are some document pages that may contain the required information.\n",
                }
            )
        else:
            content = []
        for image_path in images:
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode("utf-8")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                }
            )
        content.append({"type": "text", "text": question})
        message = {"role": "user", "content": content}
        return message

    def content2message(
        self,
        prompt: str,
        question: str,
        page_contents: list[PageContent],
        figure_contents: list[Figure],
    ) -> list:
        message_contents: list[dict[str, Any]] = [
            {"type": "text", "text": f"{prompt}{question}"}
        ]
        if figure_contents:
            message_contents.append(
                {
                    "type": "text",
                    "text": "The next are some figures ,tables or charts that may contain the required information.\n",
                }
            )
            for figure in figure_contents:
                with open(figure.image_path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode("utf-8")
                message_contents.extend(
                    [
                        {"type": "text", "text": f"{figure.text}:"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            },
                        },
                    ]
                )
        if page_contents:
            message_contents.append(
                {
                    "type": "text",
                    "text": "The next are some document pages that may contain the required information.I will give you page images and texts\n",
                }
            )
            for page in page_contents:
                with open(page.image_path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode("utf-8")
                message_contents.extend(
                    [
                        {"type": "text", "text": f"Page {page.page}:"},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            },
                        },
                    ]
                )
        messages = [{"role": "user", "content": message_contents}]
        return messages

    def query(self, messages: list) -> tuple[str, list]:
        max_retries = 10
        retry_count = 0

        while retry_count < max_retries:
            try:
                output = self.model.chat.completions.create(
                    model=self.model_name, messages=messages
                )
                output_text = output.choices[0].message.content
                if output_text is None:
                    output_text = ""
                return output_text, messages
            except (APIConnectionError, RateLimitError) as e:
                print(
                    f"Connection error occurred: {e}. Retrying ({retry_count + 1}/{max_retries})..."
                )
                retry_count += 1
                time.sleep(1)
        raise RuntimeError

    def create_figure_message(
        self, figure_contents: list[dict[str, str]], figure_prompt: str
    ):
        contents = []
        # content 内容
        # {
        #     "img_path": img_path,
        #     "caption": item.get("caption", ""),
        # }
        for content in figure_contents:
            try:
                with open(content["img_path"], "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode("utf-8")
                c = [
                    {"type": "text", "text": content["caption"]},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                    },
                ]
                contents.extend(c)
            except:
                continue
        if contents:
            contents.insert(0, {"type": "text", "text": figure_prompt})
        return contents

    def predict(self, question, texts=None, images=None, history=None) -> tuple[str, list]:  # type: ignore
        messages = self.process_message(
            question,
            texts,
            images,
            history,
        )
        output = self.model.chat.completions.create(
            model=self.model_name, messages=messages
        )
        output_text = output.choices[0].message.content
        if output_text == None:
            output_text = ""
        return output_text, messages

    def is_valid_history(self, history):  # type: ignore
        if not isinstance(history, list):
            return False
        for item in history:
            if not isinstance(item, dict):
                return False
            if "role" not in item or "content" not in item:
                return False
            if not isinstance(item["role"], str) or not isinstance(
                item["content"], list
            ):
                return False
            for content in item["content"]:
                if not isinstance(content, dict):
                    return False
                if "type" not in content:
                    return False
                if content["type"] not in content:
                    return False
        return True


class TextLLM(BaseLLM):
    # def __init__(
    #     self,
    #     api_key: str | None = os.getenv("OPENAI_API_KEY"),
    #     model_name: str = "gpt-4o",
    # ):
    #     self.model = OpenAI(api_key=api_key)
    #     self.model_name = model_name
    def __init__(
        self,
        api_key: str | None = os.getenv("DASHSCOPE_API_KEY"),
        model_name: str = "qwen-vl-plus",
    ):
        self.base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.model = OpenAI(api_key=api_key, base_url=self.base_url)
        self.create_ask_message = lambda question: {
            "role": "user",
            "content": [
                {"type": "text", "text": question},
            ],
        }
        self.create_ans_message = lambda ans: {
            "role": "assistant",
            "content": [
                {"type": "text", "text": ans},
            ],
        }
        self.model_name = model_name

    def create_text_message(self, texts, question):
        prompt = "\n".join(texts)
        message = {
            "role": "user",
            "content": f"{prompt}\n{question}",
        }
        return message

    def is_valid_history(self, history):  # type: ignore
        if not isinstance(history, list):
            return False
        for item in history:
            if not isinstance(item, dict):
                return False
            if "role" not in item or "content" not in item:
                return False
            if not isinstance(item["role"], str) or not isinstance(
                item["content"], str
            ):
                return False
        return True

    def content2message(
        self,
        prompt: str,
        question: str,
        page_contents: list[PageContent],
        figure_contents: list[Figure] = [],
    ) -> list:
        """
        如果不传入page content，则将prompt和question结合进行回答，否则生成page内容
        """
        text = ""
        if page_contents:
            for page in page_contents:
                text += f"{page.text.replace('\n',' ')} \n"
            text = f"The following is the reference content you can use. Answer the question mentioned above based on the content below.{text}\nQuestion:{question}"
        messages = [{"role": "user", "content": f"{prompt}{question}\n{text}"}]
        return messages

    def predict(self, question, history=None) -> tuple[str, list]:  # type: ignore
        messages = self.process_message(
            question=question,
            history=history,
        )
        output = self.model.chat.completions.create(
            model=self.model_name, messages=messages
        )
        output_text = output.choices[0].message.content
        if output_text == None:
            output_text = ""
        return output_text, messages

    def query(self, messages: list) -> tuple[str, list]:
        max_retries = 10
        retry_count = 0

        while retry_count < max_retries:
            try:
                output = self.model.chat.completions.create(
                    model=self.model_name, messages=messages
                )
                output_text = output.choices[0].message.content
                if output_text is None:
                    output_text = ""
                return output_text, messages
            except (APIConnectionError, RateLimitError) as e:
                print(
                    f"Connection error occurred: {e}. Retrying ({retry_count + 1}/{max_retries})..."
                )
                retry_count += 1
                time.sleep(1)
        raise RuntimeError
