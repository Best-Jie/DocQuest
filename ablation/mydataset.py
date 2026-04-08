import json
import re
from dataclasses import dataclass
from PIL import Image
import os
from datetime import datetime
import glob
from dotmap import DotMap  # type: ignore[import-untyped]


@dataclass
class PageContent:
    page: int
    image: Image.Image | None
    image_path: str
    text: str


@dataclass
class Figure:
    page: int
    image_path: str
    text: str


class BaseDataset:
    def __init__(self, config, dataset_name):
        cfg = DotMap(config)
        self.dataset_name = dataset_name
        cfg.dataset.name = dataset_name
        self.data_dir = cfg.dataset.data_dir.format(**cfg)
        cfg.dataset.data_dir = self.data_dir
        self.result_dir = cfg.dataset.result_dir.format(**cfg)
        self.extract_path = cfg.dataset.extract_path.format(**cfg)
        self.document_path = cfg.dataset.document_path.format(**cfg)
        self.sample_path = cfg.dataset.sample_path.format(**cfg)
        self.sample_with_retrieval_path = cfg.dataset.sample_with_retrieval_path.format(
            **cfg
        )
        self.question_key = cfg.dataset.question_key
        self.r_text_key = cfg.retrieval.r_text_key.format(**cfg)
        self.r_image_key = cfg.retrieval.r_image_key.format(**cfg)
        self.top_k = cfg.dataset.top_k
        self.page_id_key = cfg.dataset.page_id_key
        self.max_page = cfg.dataset.max_page
        self.max_character_per_page = cfg.dataset.max_character_per_page
        self.pdffigure2_extract_path = cfg.dataset.pdffigure2_extract_path.format(**cfg)
        self.pdffigure2_path = cfg.dataset.pdffigure2_path.format(**cfg)
        self.summary_path = cfg.dataset.summary_path.format(**cfg)
        self.sample_select_num = cfg.run_args.sample_select_num
        self.IM_FILE = (
            lambda doc_name, index: f"{self.extract_path}/{doc_name}_{index}.png"
        )
        self.TEXT_FILE = (
            lambda doc_name, index: f"{self.extract_path}/{doc_name}_{index}.txt"
        )
        self.EXTRACT_DOCUMENT_ID = lambda sample: re.sub(
            "\\.pdf$", "", sample["doc_id"]
        ).split("/")[-1]
        self.SUMMARY_FILE = (
            lambda doc_name: f"{self.summary_path}/{doc_name}_summary.md"
        )
        current_time = datetime.now()
        self.time = current_time.strftime("%Y-%m-%d-%H-%M")

    def load_data(self, use_retrieval=True):
        """从路径中加载文档 通过读取对象本身的config参数，得到数据集中的所有数据的索引，文件格式为json

        Args:
            use_retrieval (bool, optional): _description_. Defaults to True.

        Returns:
            _type_:
        """
        path = self.sample_path
        if use_retrieval:
            try:
                assert os.path.exists(self.sample_with_retrieval_path)
                path = self.sample_with_retrieval_path
            except:
                print("Use original sample path!")
        print(f"dataset path:{path}")
        assert os.path.exists(path)
        with open(path, "r") as f:
            samples = json.load(f)
        if self.sample_select_num != -1:
            samples = samples[0 : self.sample_select_num]
        return samples

    def dump_data(self, samples, use_retrieval=True):
        if use_retrieval:
            path = self.sample_with_retrieval_path
        else:
            path = self.sample_path

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(samples, f, indent=4)
        return path

    def load_latest_results(self):
        print(self.result_dir)
        path = find_latest_json(self.result_dir)
        assert isinstance(path, str)
        with open(path, "r") as f:
            samples = json.load(f)
        return samples, path

    def dump_results(self, samples):
        os.makedirs(self.result_dir, exist_ok=True)
        path = os.path.join(self.result_dir, self.time + ".json")
        print(f"save_to {path}")
        with open(path, "w") as f:
            json.dump(samples, f, indent=4)
        return path

    def get_sample_question(self, sample) -> str:
        return sample[self.question_key]

    def load_sample_retrieval_data(self, sample):
        content_list = self.load_processed_content(sample, disable_load_image=True)
        image_pages: list[PageContent] = []
        text_pages: list[PageContent] = []
        if self.r_text_key in sample:
            rerank_text_list = self.page_rank(
                sample[self.r_text_key], sample[f"{self.r_text_key}_score"]
            )
            for page in rerank_text_list[: self.top_k]:
                text_pages.append(content_list[page])
        if self.r_image_key in sample:
            rerank_image_list = self.page_rank(
                sample[self.r_image_key], sample[f"{self.r_image_key}_score"]
            )
            for page in rerank_image_list[: self.top_k]:
                image_pages.append(content_list[page])
        return text_pages, image_pages

    def page_rank(self, page_numbers: list[int], scores: list[float]):
        seen = set()
        result = []
        for num in page_numbers:
            if num not in seen:
                seen.add(num)
                result.append(num)
        return result

    def load_processed_content(
        self, sample: dict, disable_load_image=True
    ) -> list[PageContent]:
        """读取已经存储到tmp中的，经过解析的文档内容，每一页保存为content类。
        Args:
            sample (dict): _description_
            disable_load_image (bool, optional): _description_. Defaults to True.

        Returns:
            list[Content]: _description_
        """
        doc_name = self.EXTRACT_DOCUMENT_ID(sample)
        content_list = []
        for page_idx in range(self.max_page):
            im_file = self.IM_FILE(doc_name, page_idx)
            text_file = self.TEXT_FILE(doc_name, page_idx)
            if not os.path.exists(im_file):
                break
            img = None
            if not disable_load_image:
                img = self.load_image(im_file)
            txt = self.load_txt(text_file)
            content_list.append(
                PageContent(image=img, image_path=im_file, text=txt, page=page_idx + 1)
            )
        return content_list

    def load_located_contents(
        self, sample, content_names: list[str], page_ids: list[int] = []
    ):
        """
        通过location函数的返回，解析question中提到的Pages 和 figures
        """
        pattern = r"^(Figure|Table|Page) ([\w\u4e00-\u9fa5]+)$"
        contents: list[tuple[str, str]] = []
        for content in content_names:
            match = re.match(pattern, content)
            if match:
                prefix, name = match.groups()
                if prefix == "Page":
                    try:
                        page_id = int(name)
                    except ValueError as e:
                        continue
                    if page_id not in page_ids:
                        page_ids.append(page_id)
                else:
                    contents.append((prefix, name))
        doc_name = self.EXTRACT_DOCUMENT_ID(sample)
        page_contents: list[PageContent] = []
        if page_ids is not None:
            for page in page_ids:
                im_file = self.IM_FILE(doc_name, page - 1)
                text_file = self.TEXT_FILE(doc_name, page - 1)
                if not os.path.exists(im_file):
                    break
                txt = self.load_txt(text_file)
                img = self.load_image(im_file)
                page_contents.append(
                    PageContent(page=page, image=img, image_path=im_file, text=txt)
                )
        figure_list: list[Figure] = []
        try:
            with open(
                f"{self.pdffigure2_extract_path}/data/{doc_name}.json",
                "r",
                encoding="utf-8",
            ) as f:
                data = json.load(f)
                for figType, name in contents:
                    for item in data:
                        if item.get("name") == name and item.get("figType") == figType:
                            img_path = item["renderURL"]
                            figure_list.append(
                                Figure(
                                    page=item.get("page") + 1,
                                    image_path=img_path,
                                    text=item.get("caption", ""),
                                )
                            )
        except Exception as e:
            print(e)
        return page_contents, figure_list

    def load_image(self, file):
        pil_im = Image.open(file)
        return pil_im

    def load_txt(self, file):
        max_length = self.max_character_per_page
        with open(file, "r", encoding="utf-8") as file:
            content = file.read()
        content = content.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
        return content[:max_length]


def extract_time(file_path):
    file_name = os.path.basename(file_path)
    time_str = file_name.split(".json")[0]
    return datetime.strptime(time_str, "%Y-%m-%d-%H-%M")


def find_latest_json(result_dir):
    pattern = os.path.join(result_dir, "*-*-*-*-*.json")
    files = glob.glob(pattern)
    files = [f for f in files if not f.endswith("_results.json")]
    if not files:
        print(f"Json file not found at {result_dir}")
        return None
    latest_file = max(files, key=extract_time)
    return latest_file
