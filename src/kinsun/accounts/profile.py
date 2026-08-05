"""長輩檔案讀取器：一次讀取同時供應「人設」與「稱呼」。

## 為什麼不是事實提供者（2026-08-05）

這段程式的前身是 `accounts/facts.py` 的 `ElderProfileFacts`——七個事實提供者
之一，讀長輩資料列只為了產出稱呼那一句、掛在情境區塊。

人設要放進提示詞**開頭**（性格與規則分家，見 `personas.py`），`CareAgent` 就得
知道這位長輩的人設；天真做法是再查一次 `elders`，但那與稱呼那次讀取完全重複，
而正式環境的 psycopg 連線池只有 3 條（`DATABASE_POOL_MAX_SIZE=3`）。故不是複製
一份讀取，而是把那一次讀取**整個搬家**：從事實提供者清單移除，改由 `CareAgent`
在每輪開頭與情境組裝並行發動，一次讀取供應兩樣東西。全輪的資料庫讀取次數不變，
事實提供者的並行度反而由 7 降到 6。

## 稱呼那一句的措辭一字不改

`address_line` 的兩種措辭（有稱謂／只有名字）與 2026-07-17 的版本逐字相同，只是
從 `FactSection` 的條目改成獨立一行。當時的實測背景：情境沒有任何稱呼資料時，
模型每輪自行猜一個性別稱謂（同一位長輩一下被叫阿公、一下被叫阿嬤），真實使用有
一半機率叫錯。那段文字是調過的，不在這次一併重調。

⚠️ 位置變了（情境區塊尾巴 → 提示詞開頭），這是往「模型更重視」的方向移動，但仍
需人工驗收確認沒有反效果——見 `docs/superpowers/plans/2026-08-05-金孫人設.md`
的驗收清單第 6 項。
"""

from __future__ import annotations

from dataclasses import dataclass

from kinsun.personas import DEFAULT_PERSONA_ID


@dataclass(frozen=True)
class ElderProfile:
    """一位長輩的「該怎麼跟他講話」：人設 ＋ 稱呼那一句。

    `persona_id` 原樣帶出、**不在這裡做值域判斷**——退回預設是
    `personas.get_persona` 的職責，讓那個判斷只有一處。
    `address_line` 為空字串＝這位長輩沒有任何稱呼資料（查無此人、或名字與稱謂
    都是空的），提示詞就少那一句。
    """

    persona_id: str = DEFAULT_PERSONA_ID
    address_line: str = ""


class ElderProfileReader:
    """get_profile(elder_id) -> ElderProfile（查無長輩時回全預設，不拋例外）。"""

    def __init__(self, store) -> None:
        self._store = store

    def get_profile(self, elder_id: str) -> ElderProfile:
        elder = self._store.get_elder(elder_id)
        if elder is None:
            return ElderProfile()
        if elder.nickname:
            address_line = f"請用「{elder.nickname}」稱呼她／他，開頭問候也用這個稱呼。"
        elif elder.name:
            address_line = (
                f"她／他的名字是「{elder.name}」，可以自然地用名字稱呼。"
                "系統沒有性別資料，不要自行猜測用「阿公」或「阿嬤」這類稱謂，"
                "除非她／他自己說過。"
            )
        else:
            address_line = ""
        return ElderProfile(persona_id=elder.persona, address_line=address_line)
