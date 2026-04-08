import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from mydatasets.BaseDataset import BaseDataset
import toml  # type: ignore[import-untyped]
import argparse
from models.base_model import BaseLLM
from models.remote_llm import TextLLM, ImageLLM
from mydatasets.BaseDataset import BaseDataset, PageContent, Figure
import json
from tqdm import tqdm
from typing import Any
import base64
from abc import abstractmethod
import time
from dotmap import DotMap  # type: ignore[import-untyped]
import os
import concurrent.futures


class BaseAgent:
    prompt: str
    model: BaseLLM

    def __init__(self, model: BaseLLM, prompt: str):
        self.model = model
        self.prompt = prompt

    def content2messages(
        self,
        question: str,
    ) -> list:
        """
        如果不传入page content，则将prompt和question结合进行回答，否则生成page内容
        """
        messages = [{"role": "user", "content": f"{self.prompt}{question}"}]
        return messages

    @abstractmethod
    def predict(self, question: str) -> str:
        pass


class TextAgent(BaseAgent):
    def __init__(self, prompt: str):
        self.model = TextLLM()
        self.prompt = prompt

    def content2messages(
        self,
        question: str,
        page_contents: list[PageContent] = [],
    ) -> list:
        """
        如果不传入page content，则将prompt和question结合进行回答，否则生成page内容
        """
        text = ""
        if page_contents:
            for page in page_contents:
                text += f"{page.text.replace('\n',' ')} \n"
            text = f"The following is the reference content you can use. Answer the question mentioned above based on the content below.{text}\nQuestion:{question}"
        messages = [{"role": "user", "content": f"{self.prompt}{question}\n{text}"}]
        return messages

    def predict(self, question: str, page_content=[]):
        output, _ = self.model.query(
            self.content2messages(question=question, page_contents=page_content)
        )
        return output


class ImageAgent(BaseAgent):
    def __init__(self, prompt: str):
        self.model = ImageLLM()
        self.prompt = prompt

    def content2message(
        self,
        question: str,
        page_contents: list[PageContent],
        figure_contents: list[Figure],
    ) -> list:
        message_contents: list[dict[str, Any]] = [
            {"type": "text", "text": f"{self.prompt}{question}"}
        ]
        if figure_contents:

            message_contents.append(
                {
                    "type": "text",
                    "text": "The next are some figures ,tables or charts that may contain the required information.\n",
                }
            )
            for figure in figure_contents:
                if not os.path.exists(figure.image_path):
                    continue
                # 读取图片并转换为base64编码
                with open(figure.image_path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode("utf-8")
                message_contents.extend(
                    [
                        {
                            "type": "text",
                            "text": f"The following is the figure from page {figure.page}. The caption of this figure is:{figure.text},the figure is:",
                        },
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
                        {
                            "type": "text",
                            "text": f"The next is the image of Page {page.page}:",
                        },
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

    def predict(
        self,
        question: str,
        page_contents: list[PageContent] = [],
        figure_contents: list[Figure] = [],
    ) -> str:
        messages = self.content2message(
            question=question,
            page_contents=page_contents,
            figure_contents=figure_contents,
        )
        output, _ = self.model.query(messages=messages)
        return output


class GeneralAgent(BaseAgent):
    messages: list = []
    critical_prompt: str

    def __init__(self, prompt: str, critical_prompt: str):
        self.model = ImageLLM()
        self.prompt = prompt
        self.critical_prompt = critical_prompt

    def content2messages(
        self,
        question: str,
        text_page_contents: list[PageContent] = [],
        image_page_contents: list[PageContent] = [],
    ) -> list:
        message_contents: list = [{"type": "text", "text": f"{self.prompt}{question}"}]
        if text_page_contents:
            message_contents.append(
                {
                    "type": "text",
                    "text": "The next are some document pages that may contain the required information.I will give you page images and texts\n",
                }
            )
            text = ""
            for page in text_page_contents:
                text += f"{page.text.replace('\n',' ')} \n"
            message_contents.append({"type": "text", "text": text})
        if image_page_contents:
            for page in image_page_contents:
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
        message = [{"role": "user", "content": message_contents}]
        return message

    def predict(
        self,
        question: str,
        text_page_contents: list[PageContent] = [],
        image_page_contents: list[PageContent] = [],
    ) -> str:
        messages = self.content2messages(
            question=question,
            text_page_contents=text_page_contents,
            image_page_contents=image_page_contents,
        )
        output, history = self.model.query(messages=messages)
        self.messages = history
        return output

    def self_reflect(self):
        answer, _ = self.model.predict(
            question=self.critical_prompt, history=self.messages
        )  # type:ignore
        self.clean_messages()
        return answer

    def clean_messages(self):
        self.messages = []


class LocateAgent(TextAgent):
    def __init__(self, prompt: str, advice_prompt: str):
        self.advice_prompt = advice_prompt
        super().__init__(prompt)

    def content2messages(
        self, question: str, page_contents: list[PageContent] = []
    ) -> list:
        return [
            {"role": "system", "content": self.prompt},
            {"role": "user", "content": question},
        ]

    def locate(self, question: str) -> tuple[str, dict[str, str | list[str]]]:
        messages = self.content2messages(question=question, page_contents=[])
        output, _ = self.model.query(messages=messages)
        try:
            data = json.loads(output)
        except json.JSONDecodeError:
            start_idx = output.find("{")
            end_idx = output.rfind("}")
            if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
                print(f"can't find json {output}")
                data = {"modal": "General", "location": ["General"]}
            potential_json = output[start_idx : end_idx + 1]
            try:
                data = json.loads(potential_json)
            except json.JSONDecodeError as e:
                print(f"can't find json: {e}")
                data = {"modal": "General", "location": ["General"]}
        if data["modal"] == "General":
            data["modal"] = "text and image"
        advice_prompt = self.advice_prompt.format(agent_name=data["modal"])
        return advice_prompt, data


class SumAgent(TextAgent):
    def sum(self, sum_question):
        ans = self.predict(question=sum_question)
        try:
            response_dict = json.loads(ans)
            answer = response_dict.get("Answer", ans)
        except:
            answer = ans
        return answer


eval_prompt = """Question: {question}
  Predicted Answer: {answer}
  Ground Truth Answer: {gt}
  
  Please evaluate if the predicted answer is correct compared to the ground truth.
  Score the answer on:
  Binary correctness (0-1): 1 if the answer is correct, 0 if it is incorrect

  Return only a string with these scores in a dictionary and can be parsed by json.loads, e.g. {{"binary_correctness": 1}}
"""


class EvalAgent(TextAgent):
    def __init__(self, prompt: str):

        super().__init__(eval_prompt)


class DocQuestAgents:
    general_agent: GeneralAgent
    text_agent: TextAgent
    image_agent: ImageAgent
    sum_agent: SumAgent
    locate_agent: LocateAgent

    def __init__(self, config: dict):
        prompts: dict[str, str] = config["prompts"]
        self.general_agent = GeneralAgent(
            prompts["general_agent"], critical_prompt=prompts["critical_prompt"]
        )
        self.text_agent = TextAgent(prompts["text_agent"])
        self.image_agent = ImageAgent(prompts["image_agent"])
        self.sum_agent = SumAgent(prompts["sum_agent"])
        self.locate_agent = LocateAgent(
            prompts["locate_prompt"], prompts["advice_prompt"]
        )
        self.figure_prompt = prompts["figure_prompt"]
        self.eval_prompt = prompts["eval_prompt"]
        cfg = DotMap(config)
        self.ans_key = cfg.run_args.ans_key.format(**cfg)
        self.save_freq = cfg.run_args.save_freq
        self.gt_key = cfg.dataset.gt_key
        self.max_retry = cfg.run_args.max_retry

    def load_sample_retrieval_data(
        self,
        sample,
        dataset: BaseDataset,
    ):
        content_list = dataset.load_processed_content(sample, disable_load_image=True)
        image_pages: list[PageContent] = []
        text_pages: list[PageContent] = []
        top_k = dataset.top_k
        if dataset.r_text_key in sample:
            rerank_text_list = dataset.page_rank(
                sample[dataset.r_text_key], sample[f"{dataset.r_text_key}_score"]
            )
            for page in rerank_text_list[:top_k]:
                text_pages.append(content_list[page])
        if dataset.r_image_key in sample:
            rerank_image_list = dataset.page_rank(
                sample[dataset.r_image_key], sample[f"{dataset.r_image_key}_score"]
            )
            for page in rerank_image_list[:top_k]:
                image_pages.append(content_list[page])
        return text_pages, image_pages

    def predict(
        self,
        sample: dict,
        dataset: BaseDataset,
    ):
        question = dataset.get_sample_question(sample)
        text_page_content, image_page_content = self.load_sample_retrieval_data(
            sample, dataset
        )
        general_response = self.general_agent.predict(
            question=question,
            text_page_contents=text_page_content,
            image_page_contents=image_page_content,
        )
        # critical_info = self.general_agent.self_reflect()

        # start_index = critical_info.find("{")
        # end_index = critical_info.find("}") + 1
        # critical_info = critical_info[start_index:end_index]
        text_reflection = ""
        image_reflection = ""
        # try:
        #     critical_info = json.loads(critical_info)
        #     text_reflection = critical_info.get("text", "")
        #     image_reflection = critical_info.get("image", "")
        # except Exception as e:
        #     print(e)
        all_messages = "General Agent:\n" + general_response + "\n"

        reflect_prompt = ""
        # 第三步：并行执行 text_agent 和 image_agent
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_text = executor.submit(
                self.text_agent.predict,
                question + reflect_prompt + text_reflection,
                page_content=text_page_content,
            )
            future_image = executor.submit(
                self.image_agent.predict,
                question + reflect_prompt + image_reflection,
                page_contents=image_page_content,
                figure_contents=[],
            )

            text_response = future_text.result()
            image_response = future_image.result()

        # 第四步：汇总结果
        all_messages += "Text Agent:\n" + text_response + "\n"
        all_messages += "Image Agent:\n" + image_response + "\n"
        final_ans = self.sum_agent.sum(all_messages)
        sample["r_general"] = general_response
        sample["r_text"] = text_response
        sample["r_image"] = image_response
        return final_ans

    def predict_dataset(self, dataset: BaseDataset):
        samples = dataset.load_data(use_retrieval=True)
        sample_no = 0
        max_retries = self.max_retry
        for sample in tqdm(samples):
            final_ans = None
            final_messages = None
            retry_count = 0
            while retry_count <= max_retries:
                try:
                    final_ans = self.predict(sample, dataset)
                    break  # 成功则跳出循环
                except Exception as e:
                    retry_count += 1
                    print(
                        f"Error on sample {sample_no}, retry {retry_count}/{max_retries}: {e}"
                    )
                    if retry_count > max_retries:
                        final_ans = None  # 超出重试次数，置为 None
            time.sleep(1)
            sample[self.ans_key] = final_ans
            self.clean_messages()
            sample_no += 1
            if sample_no % self.save_freq == 0:
                path = dataset.dump_results(samples)
                print(f"Save {sample_no} results to {path}.")
        path = dataset.dump_results(samples)
        print(f"Save final results to {path}.")

    def clean_messages(self):
        self.general_agent.clean_messages()

    def eval(self, question: str, answer: str, ground_truth: str):
        prompt = self.eval_prompt.format(
            question=question, answer=answer, gt=ground_truth
        )
        try:
            messages = [{"role": "user", "content": f"{prompt}"}]
            generated_ans, _ = self.text_agent.model.query(messages=messages)
            result = extract_evaluation_metrics(generated_ans)
            return result
        except Exception as e:
            print(f"Error evaluating answer: {str(e)}")
            return {"binary_correctness": 0}

    def eval_dataset(self, dataset: BaseDataset):
        samples, ans_path = dataset.load_latest_results()
        samples_with_answer = []
        total_score = 0.0
        count = 0
        max_retries = self.max_retry
        try:
            for sample in tqdm(samples):
                retry_count = 0
                question = sample[dataset.question_key]
                answer = sample[self.ans_key]
                gt = sample[self.gt_key]
                if None in (question, answer, gt):
                    continue
                while retry_count <= max_retries:
                    try:
                        result = self.eval(question, answer, gt)
                        sample["binary_correctness"] = result.get(
                            "binary_correctness", 0
                        )
                        samples_with_answer.append(sample)
                        count += 1
                        total_score += sample["binary_correctness"]
                        break
                    except Exception as e:
                        time.sleep(1)
                        retry_count += 1
                        if retry_count >= max_retries:
                            count -= 1  # 如果超过最大重试次数仍未成功，则取消计数
                            break
                        print(f"Error evaluating sample: {str(e)}")
        except KeyError as e:
            print(f"{e}")
        ans_file_path_name = ans_path[:-5] + "_results.json"
        with open(ans_file_path_name, "w") as file:
            json.dump(samples_with_answer, file, indent=4)
        avg_binary_correctness = total_score / count if count > 0 else 0.0
        path = os.path.join(dataset.result_dir, "results.txt")
        with open(path, "a") as file:
            file.write("\nEvaluation Results Summary:\n")
            file.write(f"Result file: {ans_path}\n")
            file.write(f"Average Binary Correctness: {avg_binary_correctness:.3f}\n")

        print(f"Save results to {path}.")
        print(f"Average Binary Correctness: {avg_binary_correctness:.3f}\n")


def extract_evaluation_metrics(eval_str: str) -> dict[str, float | int]:
    try:
        start_index = eval_str.find("{")
        end_index = eval_str.rfind("}") + 1
        eval_str = eval_str[start_index:end_index]
        metrics = json.loads(eval_str)
        return {"binary_correctness": int(metrics.get("binary_correctness", 0))}
    except json.JSONDecodeError as e:
        return {"binary_correctness": 0}
    except Exception as e:
        return {"binary_correctness": 0}


def main(toml_cfg_path):
    with open(toml_cfg_path, "r") as f:
        dq_cfg = toml.load(f)
    parser = argparse.ArgumentParser(description="predict script")
    parser.add_argument("--dataset-name", type=str, required=True)
    parser.add_argument("--run-name", type=str, required=True)
    args = parser.parse_args()
    dq_cfg["run_args"]["run_name"] = args.run_name
    dataset = BaseDataset(dq_cfg, args.dataset_name)
    docQuestAgents = DocQuestAgents(dq_cfg)
    docQuestAgents.predict_dataset(dataset)
    docQuestAgents.eval_dataset(dataset)


if __name__ == "__main__":
    main(toml_cfg_path="config/doc_quest_config.toml")
