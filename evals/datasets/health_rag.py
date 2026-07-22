"""衛教 RAG 問答資料集：上傳成 Opik dataset，供 RAG 檢索品質實驗使用。

每筆 `input` 是長輩會問的衛教問題，`expected_output` 是理想的 grounded 回答方向
（供 ContextRecall／ContextPrecision 對照）。context 不寫死在此——實驗會實跑真實
retriever 取當次檢索到的 evidence。
"""

from __future__ import annotations

import opik

from kinsun.config import load_dotenv

DATASET_NAME = "kinsun-health-rag"

ITEMS = [
    {
        "input": "高血壓平常飲食要注意什麼",
        "expected_output": "少鹽少油、多蔬果、規律量血壓，並依醫囑服藥；不自行停藥。",
    },
    {
        "input": "糖尿病可以吃水果嗎",
        "expected_output": "可以但要適量、選低糖水果並控制份量，血糖不穩時先問醫師或營養師。",
    },
    {
        "input": "長輩要怎麼預防跌倒",
        "expected_output": "居家保持明亮、地面防滑、浴室加扶手、穿合腳鞋，並維持規律運動增強肌力。",
    },
    {
        "input": "晚上睡不著有什麼助眠的方法",
        "expected_output": "固定作息、睡前少用3C與咖啡因、放鬆身心；長期失眠建議就醫評估。",
    },
    {
        "input": "長輩需不需要打流感疫苗",
        "expected_output": "65歲以上屬高風險族群，通常建議每年接種流感疫苗，接種前可先諮詢醫師。",
    },
    {
        "input": "天氣熱長輩要怎麼補充水分",
        "expected_output": "少量多次喝水，別等口渴才喝，避免正午外出；心腎病患依醫囑控水量。",
    },
    {
        "input": "膝蓋退化性關節炎怎麼保養",
        "expected_output": "控制體重、適度低衝擊運動、避免長時間蹲跪爬樓梯，疼痛加劇時就醫評估。",
    },
    {
        "input": "高血脂要少吃哪些東西",
        "expected_output": "少吃油炸、動物內臟與高飽和脂肪食物，多蔬果全穀，配合運動與醫囑追蹤。",
    },
    {
        "input": "長輩便祕可以怎麼改善",
        "expected_output": "多喝水、多吃蔬菜纖維、規律活動與如廁習慣，持續不適則就醫。",
    },
    {
        "input": "中風有哪些警訊要注意",
        "expected_output": "臉歪、手無力、講話不清（微笑舉手說話口訣），出現就要立刻就醫。",
    },
    {
        "input": "骨質疏鬆要怎麼預防",
        "expected_output": "補鈣與維生素D、適度負重運動、多曬太陽、戒菸少酒，必要時檢測骨密度。",
    },
    {
        "input": "長輩感冒需不需要看醫生",
        "expected_output": "輕微可多休息多喝水觀察；若高燒不退、呼吸困難或症狀加重，建議盡快就醫。",
    },
]


def seed() -> None:
    client = opik.Opik()
    dataset = client.get_or_create_dataset(name=DATASET_NAME)
    dataset.insert(ITEMS)
    print(f"已上傳 {len(ITEMS)} 筆到 Opik dataset：{DATASET_NAME}")


if __name__ == "__main__":
    load_dotenv()  # 讓 opik.Opik() 讀到 .env 的 OPIK_URL_OVERRIDE 等
    seed()
