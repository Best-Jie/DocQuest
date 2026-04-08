from pathlib import Path
import json
from typing import Dict
import networkx as nx
import os
import matplotlib.pyplot as plt
from models.local_llm import LLM


class DocQuestGraph:
    """文档知识图谱构建类

    该类用于构建和管理基于文档的知识图谱。它使用大语言模型(LLM)从文本中提取实体和关系，
    并将其存储在有向图结构中。图谱可以被保存为GML格式文件，并可以生成可视化图像。

    属性:
        _graph (nx.DiGraph): NetworkX有向图对象，用于存储知识图谱
        _path_graph (str): 图谱文件的保存路径
        _extractorPrompt (Dict): 用于实体关系提取的LLM提示模板
        _log_path (str): 日志文件路径
        _llm (LLM): 大语言模型实例，用于实体关系提取
    """

    _graph: nx.DiGraph
    _path_graph: str
    _extractorPrompt: Dict
    _log_path: str
    _llm: LLM

    def __init__(
        self,
        llm: LLM,
        extractorPrompt: Dict[str, str],
        graph_file_path: str,
        log_path: str,
    ) -> None:
        self.llm = llm
        self._extractorPrompt = extractorPrompt
        self._log_path = log_path
        self._path_graph = graph_file_path
        if os.path.exists(graph_file_path):
            # 文件存在，读取已有的有向图
            self._graph = nx.read_gml(graph_file_path, label="id")
        else:
            # 文件不存在，创建一个空的有向图
            self._graph = nx.DiGraph()

    def addData(self, text):
        pass

    def addDataFromFolder(self, folder_path, file_name):
        i = -1
        folderPath = Path(folder_path)
        while True:
            i += 1
            page_name = f"{file_name}_{i}"

            file_path = folderPath / Path(f"{page_name}.txt")
            if not (file_path.exists() | file_path.is_file()):
                break
            with file_path.open("r", encoding="utf-8") as file:
                text = file.read().replace("\n", " ")
            user_prompt = self._extractorPrompt["user"]
            message = [
                {
                    "role": "system",
                    "content": self._extractorPrompt["system"],
                },
                {"role": "system", "content": user_prompt.format(text=text)},
            ]
            r = (
                self.llm.query(message=message)
                .replace("<|START|>", "")
                .replace("<|COMPLETE|>", "")
                .replace("\n", "")
            )
            try:
                nodes = json.loads(r)
            except Exception as e:
                print(e)
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(f"{text}\n")
                    f.write(f"{r}\n")
                continue
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(f"{text}\n")
                f.write(f"{r}\n")
                for e in nodes:
                    f.write(f"|{e['entity_name']} <|> {e['relation_with_document']}\n")
            self._graph.add_node(page_name, type="scene", content=text)
            for node in nodes:
                self._graph.add_node(node["entity_name"], type="entity")
                self._graph.add_edge(
                    node["entity_name"],
                    page_name,
                    relation=node["relation_with_document"],
                )

        nx.write_gml(self._graph, self._path_graph)

    def drawGraph(self, path_img_save: str):
        nx.draw(self._graph, with_labels=True, font_size=5)
        plt.savefig(path_img_save, format="PNG", dpi=300)

    def graphSearch(self, entity_name: str, relation_name: str) -> str:
        """搜索图谱中与指定实体特定关系的场景节点

        Args:
            entity_name (str): 要搜索的实体名称

        Returns:
            str: 返回与实体相关的场景节点的内容，如果未找到则返回空字符串
        """
        texts = [
            neighbor
            for neighbor in self._graph.neighbors(entity_name)
            if self._graph.get_edge_data(entity_name, neighbor).get("relation")
            == relation_name
        ]
        if texts:
            return "\n".join(texts)
        return ""
