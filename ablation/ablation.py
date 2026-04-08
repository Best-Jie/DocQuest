from vllm import LLM, SamplingParams
import os
from PIL import Image
import base64
from mydataset import PageContent, BaseDataset
from tqdm import tqdm
from dotmap import DotMap
from typing import Any
from local_models import Qwen25VL
import argparse
import toml
import json
from torch.cuda import OutOfMemoryError

text_prompt = """
You are a text analysis agent. Your job is to extract key information from the text and use it to answer the user’s question accurately. Here are the steps to follow:
Extract key details: Focus on the most important facts, data, or ideas related to the question.
Understand the context: Pay attention to the meaning and details.
Provide a clear answer: Use the extracted information to give a concise and relevant response to user's question.
Remeber you can only get the information from the text provided, so maybe other agents can help you with the image information.
If the provided reference content cannot answer the question, do not add any extra explanation, directly output "not answerable".
Question:
"""
image_prompt = """
You are an advanced image processing agent specialized in analyzing and extracting information from images. The images may include document screenshots, illustrations, or photographs. Your primary tasks include:
Extracting textual information from images using Optical Character Recognition (OCR).
Analyzing visual content to identify relevant details (e.g., objects, patterns, scenes).
Combining textual and visual information to provide an accurate and context-aware answer to user's question.
Remeber you can only get the information from the images provided, so maybe other agents can help you with the text information.
If the provided reference content cannot answer the question, do not add any extra explanation, directly output "not answerable".
Question:
"""
eval_prompt = """
Question: {question}
Predicted Answer: {answer}
Ground Truth Answer: {gt}

Please evaluate if the predicted answer is correct compared to the ground truth, considering the following criteria:

- Score based on whether the Predicted Answer is factually and logically consistent with the Ground Truth Answer.
- Score the answer on: Binary correctness (0-1): 1 if the answer is correct, 0 if it is incorrect
- If the answer is not comprehensive, it is also considered an answer error.
Return only a JSON-parsable string in the format: {{"binary_correctness": <score>}}
Output:
"""


class Ablation:
    def __init__(self, config: dict):
        prompts: dict[str, str] = config["prompts"]
        cfg = DotMap(config)
        self.ans_key = cfg.run_args.ans_key.format(**cfg)
        self.save_freq = cfg.run_args.save_freq
        self.gt_key = cfg.dataset.gt_key
        self.max_retry = cfg.run_args.max_retry
        self.model = Qwen25VL()
        self.eval_prompt = prompts["eval_prompt"]

    def predict(self, sample, dataset: BaseDataset, page_num: int = -1):

        question = dataset.get_sample_question(sample)
        pages = dataset.load_processed_content(sample)
        if page_num != -1:
            pages = pages[:page_num]
        image_paths = [p.image_path for p in pages]
        return self.model.query(image_paths, question, image_prompt)

    def predict_dataset(self, dataset: BaseDataset):
        samples = dataset.load_data(use_retrieval=True)
        sample_no = 0
        for sample in tqdm(samples):
            final_ans = None
            try:
                final_ans = self.predict(sample, dataset)
            except OutOfMemoryError:
                final_ans = self.predict(sample, dataset, 1)
            except Exception as e:
                final_ans = None
            sample[self.ans_key] = final_ans
            sample_no += 1
            if sample_no % self.save_freq == 0:
                path = dataset.dump_results(samples)
                print(f"Save {sample_no} results to {path}.")
        path = dataset.dump_results(samples)
        print(f"Save final results to {path}.")

    def eval(self, question: str, answer: str, ground_truth: str):
        prompt = self.eval_prompt.format(
            question=question, answer=answer, gt=ground_truth
        )
        try:
            generated_ans = self.model.query([], "", prompt)
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
        for sample in tqdm(samples):
            question = sample.get(dataset.question_key)
            answer = sample.get(self.ans_key)
            gt = sample[self.gt_key]
            if isinstance(answer, list):
                answer = answer[0]
            if None in (question, answer, gt):
                continue
            try:
                result = self.eval(question, answer, gt)
                sample["binary_correctness"] = result.get("binary_correctness", 0)
                samples_with_answer.append(sample)
                total_score += sample["binary_correctness"]
            except Exception as e:
                print(f"Error evaluating sample: {str(e)}")
                continue
            count += 1
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


if __name__ == "__main__":
    with open("/home/cjy/DocQuest/DocQuest/config/doc_quest_config.toml", "r") as f:
        dq_cfg = toml.load(f)
    parser = argparse.ArgumentParser(description="predict script")
    parser.add_argument("--dataset-name", type=str, required=True)
    parser.add_argument("--run-name", type=str, required=True)
    args = parser.parse_args()
    dq_cfg["run_args"]["run_name"] = args.run_name
    dataset = BaseDataset(dq_cfg, args.dataset_name)
    agents = Ablation(dq_cfg)
    agents.predict_dataset(dataset)
    agents.eval_dataset(dataset)
