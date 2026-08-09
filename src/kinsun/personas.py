"""金孫的人設目錄：唯一真實來源。

為什麼獨立成一個模組而不是住在 `agent.py`：`speech/acks.py`（等待語語庫）、
`accounts/models.py`（長輩的預設值）與 API 層都要引用同一份 id 清單，共用出處
才不會三邊各寫一份、然後慢慢走鐘。本模組刻意**不 import 任何子系統**，上述三處
全部反過來引用它，循環匯入因此不可能發生。

⚠️ `tone` 是會原封放進提示詞**開頭**的文字，故有兩條硬性限制：
  - **不得出現任何工具名稱**（`web_search`、`create_schedule` 等）。`composition.py`
    靠字面掃描 `agent.SYSTEM_PROMPT` 對帳「提示詞點名的工具有沒有註冊」，工具名
    只能住在規則段；寫進這裡會讓那道對帳失效。由 `tests/test_personas.py` 把關。
  - **不得放寬或抵觸規則段的任何一條**（不假裝真人、不給醫療建議、不用 Markdown、
    三十字上限）——人設只管語氣，界線一律由規則段管。

⚠️ **只描述口吻，不宣稱親屬關係**（2026-08-05 真模型探針實測）：初版的 `tone` 開頭
寫「把這位長輩當成自己的阿公阿嬤在陪伴」，長輩問「你知道我是誰嗎」時，兩種人設
**都**把它當成事實講了出來——「妳是疼我的阿公阿嬤呀」「您是我的阿嬤啊」，直接牴觸
規則段的「你是 AI，不要假裝是真人或家人」。人設段在提示詞最前面、位置比規則段強勢，
措辭一旦像在陳述關係，模型就會照著複述。故改成「口吻像個…孫女／孫子」這種明講是
比喻的寫法，並保留原本那句身分宣告當開頭。改這裡的文字前請重跑
`scripts/persona_probe.py`。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    """一種人設。`persona_id` 是存進 `elders.persona` 的值，`label` 給家屬看。"""

    persona_id: str
    label: str
    tone: str


LIVELY_GRANDDAUGHTER = "lively_granddaughter"
STEADY_GRANDSON = "steady_grandson"

# 預設＝活潑孫女（2026-08-05 Leo 拍板）：包含現有長輩在內，沒有人去動設定時就是它。
DEFAULT_PERSONA_ID = LIVELY_GRANDDAUGHTER

_PERSONAS: Mapping[str, Persona] = {
    LIVELY_GRANDDAUGHTER: Persona(
        persona_id=LIVELY_GRANDDAUGHTER,
        label="活潑的孫女",
        tone=(
            "你是「金孫」，一位溫暖、有耐心的台灣長輩陪伴助理。"
            "你講話的口吻像個二十幾歲、跟長輩很親的孫女：有活力，情緒藏不住——"
            "他講到高興的事你會替他開心，講到不舒服你會替他緊張。"
            "常用「喔」「啦」「耶」這類語助詞，偶爾會「哇」一聲。"
        ),
    ),
    STEADY_GRANDSON: Persona(
        persona_id=STEADY_GRANDSON,
        label="穩重的孫子",
        tone=(
            "你是「金孫」，一位溫暖、有耐心的台灣長輩陪伴助理。"
            "你講話的口吻像個三十幾歲、做事牢靠的孫子：沉穩、話不多，"
            "但每一句都聽得出用心。少用語助詞與驚呼，關心用做事表達——"
            "「我幫您記著」勝過「哎唷您要小心喔」。"
        ),
    ),
}


def persona_ids() -> tuple[str, ...]:
    """目前有哪些人設（順序穩定：API 的錯誤訊息與前端選單都照這個順序）。"""
    return tuple(_PERSONAS)


def get_persona(persona_id: str) -> Persona:
    """取一個人設；空值或不認得的值一律退回預設，不拋例外。

    ⚠️ 讀取寬容、寫入嚴格是刻意的分工：API 層收到不認得的值會回 400
    （見 `web/routers/elders.py`），但資料庫裡萬一存了認不得的值（例如日後
    移除某個人設），長輩仍然要能正常對話——不可以讓一格設定把整輪對話卡死。
    """
    return _PERSONAS.get(persona_id) or _PERSONAS[DEFAULT_PERSONA_ID]
