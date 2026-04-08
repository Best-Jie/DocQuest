import os

os.environ["CUDA_VISIBLE_DEVICES"] = "1,0"
from modelscope import Qwen2_5_VLForConditionalGeneration, AutoTokenizer, AutoProcessor
from qwen_vl_utils import process_vision_info
import torch
from abc import ABC, abstractmethod
from mydataset import PageContent
from accelerate import infer_auto_device_map, init_empty_weights
from transformers import BitsAndBytesConfig

# default: Load the model on the available device(s)


# We recommend enabling flash_attention_2 for better acceleration and memory saving, especially in multi-image and video scenarios.


# default processer


# The default range for the number of visual tokens per image in the model is 4-16384.
# You can set min_pixels and max_pixels according to your needs, such as a token range of 256-1280, to balance performance and cost.
# min_pixels = 256*28*28
# max_pixels = 1280*28*28
# processor = AutoProcessor.from_pretrained("Qwen/Qwen2.5-VL-3B-Instruct", min_pixels=min_pixels, max_pixels=max_pixels)


# Preparation for inference


class LocalModel(ABC):
    @abstractmethod
    def query(self, page_contents: list[PageContent], prompt: str, question: str):
        pass


class Qwen2_5VL(LocalModel):
    def __init__(self) -> None:
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            "Qwen/Qwen2.5-VL-7B-Instruct",
            torch_dtype=torch.bfloat16,
            attn_implementation="sdpa",
            device_map="auto",
        )
        print(self.model.hf_device_map)
        self.processor = AutoProcessor.from_pretrained("Qwen/Qwen2.5-VL-7B-Instruct")

    def query(self, page_contents: list[PageContent], prompt: str, question: str):
        contents = []
        contents.append(
            {"type": "text", "text": prompt + question},
        )
        if page_contents:
            image_paths = [p.image_path for p in page_contents]
            for image_path in image_paths:
                contents.append(
                    {
                        "type": "image",
                        "image": f"file:///{image_path}",
                    }
                )
        messages = [{"role": "user", "content": contents}]
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, _ = process_vision_info(messages)
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=None,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to("cuda")

        # Inference: Generation of the output
        generated_ids = self.model.generate(**inputs, max_new_tokens=128)
        generated_ids_trimmed = [
            out_ids[len(in_ids) :]
            for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
        return output_text[0]


class Qwen25VL:
    def __init__(self) -> None:
        # self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        #     "Qwen/Qwen2.5-VL-7B-Instruct",
        #     torch_dtype=torch.bfloat16,
        #     attn_implementation="sdpa",
        #     device_map="auto",
        # )
        # print(self.model.hf_device_map)
        # self.processor = AutoProcessor.from_pretrained("Qwen/Qwen2.5-VL-7B-Instruct")
        bnb_8bit = BitsAndBytesConfig(
            load_in_8bit=True,  # 权重→INT8
            llm_int8_threshold=6.0,  # 默认即可
        )
        # with init_empty_weights():
        #     self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        #         "Qwen/Qwen2.5-VL-7B-Instruct",
        #         torch_dtype=torch.bfloat16,
        #         attn_implementation="sdpa",
        #         quantization_config=bnb_8bit,
        #     )

        # device_map = infer_auto_device_map(
        #     self.model,
        #     max_memory={0: "10GiB", 1: "10GiB"},  # 给每张卡留一点 buffer
        #     no_split_module_classes=["Qwen2DecoderLayer"],  # 保持整层不切碎
        # )

        # self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        #     "Qwen/Qwen2.5-VL-7B-Instruct",
        #     torch_dtype=torch.bfloat16,
        #     attn_implementation="sdpa",
        #     device_map=device_map,  # 用自定义 map
        #     offload_folder="./offload",  # 如果还不够，可把部分层 offload 到 CPU
        #     quantization_config=bnb_8bit,
        # )
        self.model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            "Qwen/Qwen2.5-VL-7B-Instruct",
            torch_dtype=torch.bfloat16,
            attn_implementation="sdpa",
            device_map="auto",  # 或 device_map=你自己算出的 dict
            max_memory={0: "10GiB", 1: "10GiB"},
            offload_folder="./offload",
            quantization_config=bnb_8bit,
        )

    def query(self, image_paths: list[str], question, prompt):
        contents = []
        contents.append(
            {"type": "text", "text": prompt + question},
        )
        for image_path in image_paths:
            contents.append(
                {
                    "type": "image",
                    "image": f"file:///{image_path}",
                }
            )
        messages = [{"role": "user", "content": contents}]
        text = self.processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        image_inputs, _ = process_vision_info(messages)
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=None,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to("cuda")

        # Inference: Generation of the output
        generated_ids = self.model.generate(**inputs, max_new_tokens=128)
        generated_ids_trimmed = [
            out_ids[len(in_ids) :]
            for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        output_text = self.processor.batch_decode(
            generated_ids_trimmed,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
        return output_text[0]
