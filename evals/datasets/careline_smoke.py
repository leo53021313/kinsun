"""最小長照問答冒煙資料集：上傳成 Opik dataset，供實驗重複使用。"""

from __future__ import annotations

import opik

DATASET_NAME = "kinsun-careline-smoke"

ITEMS = [
    {
        "input": "阿嬤問她高血壓可以吃柚子嗎",
        "expected_output": "提醒柚子與部分降血壓藥會交互作用，建議先問醫師或藥師，不要自行決定。",
    },
    {
        "input": "阿公說他忘記今天吃過藥沒",
        "expected_output": "溫和安撫，建議看藥盒或問家人，不要重複服藥。",
    },
    {
        "input": "長輩問附近有什麼好玩的",
        "expected_output": "口語閒聊式回應，不編造不存在的地點。",
    },
]


def seed() -> None:
    client = opik.Opik()
    dataset = client.get_or_create_dataset(name=DATASET_NAME)
    dataset.insert(ITEMS)
    print(f"已上傳 {len(ITEMS)} 筆到 Opik dataset：{DATASET_NAME}")


if __name__ == "__main__":
    seed()
