import multiprocessing

multiprocessing.set_start_method("spawn", force=True)
import os
from typing import List
from transformers import AutoProcessor
from vllm import LLM, SamplingParams
from qwen_vl_utils import process_vision_info


class Qwen25VL:
    """
    本地 vLLM 加载的 Qwen2.5-VL 推理封装
    用法：
        model = Qwen25VL("<本地权重路径>", gpu_memory=0.9)
        answer = model.query(
                    image_paths=["a.jpg", "b.jpg"],
                    prompt="请你根据以下图片",
                    question="描述两张图的共同点和区别")
    """

    def __init__(
        self,
        model_path: str,
        max_model_len: int = 4096,
        gpu_memory: float = 0.9,
        tensor_parallel_size: int = 1,
    ):
        self.llm = LLM(
            model=model_path,
            limit_mm_per_prompt={"image": 20, "video": 0},
            tensor_parallel_size=tensor_parallel_size,
            gpu_memory_utilization=gpu_memory,
            max_model_len=max_model_len,
            trust_remote_code=True,
            cpu_offload_gb=40,
        )
        self.processor = AutoProcessor.from_pretrained(
            model_path, trust_remote_code=True
        )

    def query(
        self,
        image_paths: List[str],
        prompt: str = "",
        question: str = "",
        max_tokens: int = 512,
        temperature: float = 0.2,
    ) -> str:
        # 1. 组装对话
        content = []
        for p in image_paths:
            content.append({"type": "image", "image": f"file://{os.path.abspath(p)}"})
        if prompt:
            content.append({"type": "text", "text": prompt})
        if question:
            content.append({"type": "text", "text": question})

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": content},
        ]

        # 2. 预处理
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, _ = process_vision_info(messages)

        # 3. 推理
        sampling = SamplingParams(
            max_tokens=max_tokens, temperature=temperature, top_p=0.95
        )
        outputs = self.llm.generate(
            prompts=[text],
            multi_modal_data={"image": image_inputs},
            sampling_params=sampling,
        )
        return outputs[0].outputs[0].text.strip()


# 快速测试
if __name__ == "__main__":
    mdl = Qwen25VL("Qwen/Qwen2.5-VL-7B-Instruct")
    ans = mdl.query(
        image_paths=[
            "/home/cjy/DocQuest/DocQuest/tmp/FetaTab/115th United States Congress_0.png",
            "/home/cjy/DocQuest/DocQuest/tmp/FetaTab/115th United States Congress_1.png",
        ],
        prompt="下面给出两张图片",
        question="请总结它们的共同点和区别",
    )
    print(ans)
