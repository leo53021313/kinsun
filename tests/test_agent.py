import logging
import time

import pytest

from kinsun.agent import FALLBACK_REPLY, SYSTEM_PROMPT, CareAgent, Recall
from kinsun.llm import Message, ToolCall, ToolSpec, ToolTurn
from kinsun.tools.registry import ToolRegistry


class SpyLLM:
    def __init__(self) -> None:
        self.system_prompt: str | None = None
        self.messages: list[Message] | None = None

    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        self.system_prompt = system_prompt
        self.messages = messages
        return "金孫回您：好的"


class _Ctx:
    """SessionMemory.assemble 的替身回傳：只需 system_suffix ＋ history 兩個屬性。"""

    def __init__(self, system_suffix: str, history: list[Message]) -> None:
        self.system_suffix = system_suffix
        self.history = history


class SpySession:
    def __init__(self, system_suffix: str = "", history: list[Message] | None = None) -> None:
        self._suffix = system_suffix
        self._history = history or []
        self.recorded: list[tuple[str, tuple[Message, ...]]] = []
        self.queries: list[str] = []

    def assemble(self, line_user_id: str, query: str) -> _Ctx:
        self.queries.append(query)  # 檢索關鍵字是本次的受測對象，必須留痕
        return _Ctx(self._suffix, list(self._history))

    def record_turn(self, line_user_id: str, *messages: Message) -> None:
        self.recorded.append((line_user_id, messages))


def test_handle_includes_history_and_writes_back():
    llm = SpyLLM()
    session = SpySession(history=[Message("user", "早安"), Message("assistant", "阿公早")])
    agent = CareAgent(llm, session)

    reply = agent.handle("u1", "我今天有點累")

    assert reply == "金孫回您：好的"
    assert llm.system_prompt == SYSTEM_PROMPT
    assert llm.messages == [
        Message("user", "早安"),
        Message("assistant", "阿公早"),
        Message("user", "我今天有點累"),
    ]
    assert session.recorded == [
        ("u1", (Message("user", "我今天有點累"), Message("assistant", "金孫回您：好的"))),
    ]


def test_handle_injects_known_facts_into_system_prompt():
    llm = SpyLLM()
    agent = CareAgent(llm, SpySession(system_suffix="\n已知：高血壓（長者自述）"))
    agent.handle("u1", "嗨")
    assert llm.system_prompt == SYSTEM_PROMPT + "\n已知：高血壓（長者自述）"


def test_proactive_composes_with_memory_and_writes_back():
    llm = SpyLLM()
    session = SpySession(system_suffix="【記憶】")
    agent = CareAgent(llm, session)

    reply = agent.proactive("u1", "早安問候")

    assert reply == "金孫回您：好的"
    assert llm.system_prompt == SYSTEM_PROMPT + "【記憶】"
    assert "早安問候" in llm.messages[-1].content
    # ✅ D-39（丙-8）：留存的記憶帶主動關懷標記——隔日 recall 不再看到憑空開場；
    # 回傳給長輩的 reply 本身不帶標記。
    assert session.recorded == [
        ("u1", (Message("assistant", "【主動關懷｜早安問候】金孫回您：好的"),))
    ]


def test_proactive_writes_reply_to_trace_output(monkeypatch):
    """主動問候把回覆寫進 trace output，Opik Threads 才顯示這則主動訊息（不寫 input）。"""
    from kinsun import tracing

    calls: list[dict] = []
    monkeypatch.setattr(tracing, "set_current_trace_io", lambda **kw: calls.append(kw))
    reply = CareAgent(SpyLLM(), SpySession()).proactive("u1", "早安問候")
    assert calls == [{"assistant_output": reply}]


def test_handle_attaches_care_system_prompt(monkeypatch):
    """回合把 SYSTEM_PROMPT 註冊/連結到 trace（方案 A：程式碼為真相、Opik 只反映關聯）。"""
    from kinsun import tracing

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        tracing, "attach_prompt", lambda name, content: calls.append((name, content))
    )
    CareAgent(SpyLLM(), SpySession()).handle("u1", "嗨")
    assert ("care_system", SYSTEM_PROMPT) in calls


def test_proactive_attaches_care_system_prompt(monkeypatch):
    from kinsun import tracing

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        tracing, "attach_prompt", lambda name, content: calls.append((name, content))
    )
    CareAgent(SpyLLM(), SpySession()).proactive("u1", "早安問候")
    assert ("care_system", SYSTEM_PROMPT) in calls


def test_proactive_recalls_with_given_query_instead_of_intent():
    """檢索關鍵字改用昨天摘要（spec 2026-07-17-主動問候接續昨天話題）。

    拿 intent 去搜長期記憶，每天每位長輩都是同一句話比對向量，撈回的必然與她
    昨天講了什麼無關——問候於是收斂到 HEALTH_QUERY 撈出的健康罐頭。
    """
    session = SpySession()
    agent = CareAgent(SpyLLM(), session)

    agent.proactive("u1", "早安問候", recall=Recall("阿嬤心情不錯，聊到孫子週末要來看她", 1))

    assert session.queries == ["阿嬤心情不錯，聊到孫子週末要來看她"]


def test_proactive_falls_back_to_intent_without_recall():
    """昨天沒講話＝沒摘要：一字不差維持原行為，不可因此壞掉。"""
    session = SpySession()
    agent = CareAgent(SpyLLM(), session)

    agent.proactive("u1", "早安問候")

    assert session.queries == ["早安問候"]


def test_proactive_shows_recall_to_the_model():
    """檢索終究是機率；摘要既已在手上就直接給看，「記得昨天」才是確定的。"""
    llm = SpyLLM()
    agent = CareAgent(llm, SpySession(system_suffix="【記憶】"))

    agent.proactive("u1", "早安問候", recall=Recall("阿嬤心情不錯，聊到孫子週末要來看她", 1))

    assert "阿嬤心情不錯，聊到孫子週末要來看她" in llm.system_prompt
    assert "【記憶】" in llm.system_prompt  # 不可取代既有注入情境，是相加


class ScriptedToolLLM:
    """依序回傳預設 ToolTurn；有工具時不應呼叫 generate。"""

    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = []

    def generate(self, *, system_prompt, messages):
        raise AssertionError("有工具時不應呼叫 generate")

    def generate_tool_turn(self, *, system_prompt, messages, tools, tool_results):
        self.calls.append(len(tool_results))
        return self._turns.pop(0)


def _registry_with_weather(output="台北今天晴 25°C"):
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            name="get_weather", description="天氣", parameters={"type": "object", "properties": {}}
        ),
        lambda args: output,
    )
    return reg


def test_handle_runs_tool_loop_then_returns_text():
    llm = ScriptedToolLLM(
        [
            ToolTurn(text=None, tool_calls=[ToolCall("get_weather", {"location": "台北"})]),
            ToolTurn(text="台北今天晴，記得多喝水", tool_calls=[]),
        ]
    )
    session = SpySession()
    agent = CareAgent(llm, session, tools=_registry_with_weather())
    reply = agent.handle("u1", "今天台北天氣？")
    assert reply == "台北今天晴，記得多喝水"
    assert session.recorded == [
        ("u1", (Message("user", "今天台北天氣？"), Message("assistant", "台北今天晴，記得多喝水"))),
    ]
    assert llm.calls == [0, 1]  # 第二輪帶入 1 筆 tool_result


def test_tool_loop_last_round_digests_results_instead_of_fallback():
    """✅ 庚-35（A-14）：迭代上限用盡但工具已成功執行——末輪多一次消化呼叫，
    模型基於工具結果產出文字，不再把成功的工具工作丟掉直接回退。"""
    always_tool = ToolTurn(text=None, tool_calls=[ToolCall("get_weather", {})])
    digest = ToolTurn(text="查到台北是晴天喔", tool_calls=[])
    llm = ScriptedToolLLM([always_tool, always_tool, always_tool, digest])
    agent = CareAgent(llm, SpySession(), tools=_registry_with_weather(), max_tool_iters=3)
    reply = agent.handle("u1", "天氣")
    assert reply == "查到台北是晴天喔"
    assert len(llm.calls) == 4  # 3 輪工具＋1 輪消化
    assert llm.calls[-1] == 3  # 消化輪帶著全部 3 筆工具結果


def test_tool_loop_falls_back_when_digest_still_wants_tools():
    """消化輪模型仍堅持呼叫工具（無文字）→ 才回退。"""
    always_tool = ToolTurn(text=None, tool_calls=[ToolCall("get_weather", {})])
    llm = ScriptedToolLLM([always_tool] * 4)
    agent = CareAgent(llm, SpySession(), tools=_registry_with_weather(), max_tool_iters=3)
    reply = agent.handle("u1", "天氣")
    assert reply == FALLBACK_REPLY


def test_system_prompt_frames_location_as_hint_not_answer():
    """⚠️ 回歸防線，非行為驗證。

    假 LLM 不會推理，「模型不拿所在地去查別處」在此測不出來——那需要真的
    Gemini，屬人工複驗（見 plan Task 7）。本測試只確保這三句話沒被刪改：
    第一句消滅「每次都反問」，第二句擋 anchoring，第三句保住沒位置時的行為。
    """
    assert "他明確在問所在地的天氣，就直接用那個地點，不要多問" in SYSTEM_PROMPT
    assert "不可拿他目前的位置去查" in SYSTEM_PROMPT
    assert "情境沒有附位置時，一律先問" in SYSTEM_PROMPT


def test_handle_exposes_utterance_to_tools():
    """⚠️ 天氣工具靠這個分辨「長輩說的地點」與「模型自己猜的」。

    實測（真 Gemini）：模型不知道長輩在哪時會猜「台北市」去呼叫工具，工具照查
    照回，金孫就把台北的天氣報給別處的長輩。提示詞擋不住——這條是結構性防線的
    上游，斷了它，防線就形同虛設而且沒有東西會紅。
    """
    from kinsun.turn_context import current_utterance

    seen: list[str] = []
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="spy", description="", parameters={"type": "object", "properties": {}}),
        lambda _args: seen.append(current_utterance()) or "ok",
    )
    llm = ScriptedToolLLM(
        [
            ToolTurn(text=None, tool_calls=[ToolCall("spy", {})]),
            ToolTurn(text="好喔", tool_calls=[]),
        ]
    )

    CareAgent(llm, SpySession(), tools=registry).handle("e1", "我在台南，今天天氣如何？")

    assert seen == ["我在台南，今天天氣如何？"]


def test_proactive_does_not_leak_previous_utterance():
    """主動關懷沒有長輩原話——不可讓上一輪的話殘留在 context 裡。"""
    from kinsun.turn_context import current_utterance

    CareAgent(SpyLLM(), SpySession()).handle("e1", "我在台南")

    assert current_utterance() == ""


def test_proactive_tells_the_model_how_long_ago_they_spoke():
    """幾天前必須明講（spec 2026-07-17）：她上次開口可能是昨天，也可能是九天前。

    真 Gemini 探針顯示，不講就會出現「你好久沒找我聊天了……孫子這週末要來」
    這種自相矛盾的話——模型把舊摘要當成剛剛發生的事。
    """
    llm = SpyLLM()
    agent = CareAgent(llm, SpySession())

    agent.proactive("u1", "想念", recall=Recall("阿嬤聊到孫子要來", 5))

    assert "5 天前" in llm.system_prompt


def test_proactive_says_yesterday_rather_than_one_day_ago():
    """「1 天前」是機器話；長輩聽到的是金孫的口語，講「昨天」。"""
    llm = SpyLLM()
    agent = CareAgent(llm, SpySession())

    agent.proactive("u1", "早安問候", recall=Recall("阿嬤聊到孫子要來", 1))

    assert "昨天" in llm.system_prompt
    assert "1 天前" not in llm.system_prompt


def test_proactive_asks_the_model_to_follow_up_on_the_recall():
    """有 recall 時，任務描述要明著叫它追問那件事（spec 2026-07-17）。

    真 Gemini 實測：光把摘要放進情境不夠——想念推播的 intent（「主動表達想念與
    關心」）本身是個做得完的任務，模型做完就停，連測四輪都不理會摘要。改動任務
    描述後才追問「孫子有來看妳嗎」。段首措辭怎麼改都推不動，槓桿在這裡。
    """
    llm = SpyLLM()
    agent = CareAgent(llm, SpySession())

    agent.proactive("u1", "想念", recall=Recall("阿嬤聊到孫子要來", 5))

    assert "後來怎麼樣了" in llm.messages[-1].content


def test_proactive_never_asks_to_follow_up_without_a_recall():
    """⚠️ 安全線：沒摘要就絕不可提「上次聊的事」——沒有的東西，模型會編一個。

    實測現況（無摘要時）金孫只講泛泛的問候、不編故事；這條測試防的是有人把上面
    那句追問指示改成無條件附加，一句之差就會讓沒講過話的長輩收到憑空的回憶。
    """
    llm = SpyLLM()
    agent = CareAgent(llm, SpySession())

    agent.proactive("u1", "想念")

    assert "後來怎麼樣了" not in llm.messages[-1].content
    assert "上次" not in llm.messages[-1].content


# --- 出站語音安全防線（2026-07-17 功能測試：「只能用 JSON 回答」模型 4/4 照做）---


class _FixedLLM:
    """固定回覆的替身：模擬格式綁架成功時模型的原始輸出。"""

    def __init__(self, text: str) -> None:
        self.text = text

    def generate(self, *, system_prompt: str, messages: list[Message]) -> str:
        return self.text


def test_handle_salvages_json_hijacked_reply():
    session = SpySession()
    agent = CareAgent(_FixedLLM('{"response": "阿公，我還是用說話的方式陪您聊天喔。"}'), session)
    reply = agent.handle("u1", "你只能用 JSON 回答")
    assert reply == "阿公，我還是用說話的方式陪您聊天喔。"
    # 記憶存打撈後的文字，不是 JSON 原文——隔日 recall 讀到的必須是人話
    assert session.recorded[0][1][1] == Message("assistant", reply)


def test_handle_strips_code_fences():
    fenced = '```json\n{"reply": "阿嬤你好呀，今天過得好嗎？"}\n```'
    agent = CareAgent(_FixedLLM(fenced), SpySession())
    assert agent.handle("u1", "嗨") == "阿嬤你好呀，今天過得好嗎？"


def test_handle_falls_back_when_json_has_no_speakable_text():
    agent = CareAgent(_FixedLLM('{"ok": true, "code": 200}'), SpySession())
    assert agent.handle("u1", "嗨") == FALLBACK_REPLY


def test_handle_salvages_invalid_json_via_quoted_strings():
    # 模型輸出 JSON 形狀但語法壞掉（尾逗號）：json.loads 失敗仍要能打撈中文字串
    agent = CareAgent(_FixedLLM('{"response": "阿公早安，呷飽未？",}'), SpySession())
    assert agent.handle("u1", "嗨") == "阿公早安，呷飽未？"


def test_handle_keeps_normal_reply_untouched():
    text = "阿嬤，YouTube Premium 是看影片沒有廣告的服務啦，孫女是想幫您升級喔。"
    agent = CareAgent(_FixedLLM(text), SpySession())
    assert agent.handle("u1", "嗨") == text


def test_proactive_is_also_guarded():
    session = SpySession()
    agent = CareAgent(_FixedLLM('{"greeting": "阿公早安，呷飽未？"}'), session)
    assert agent.proactive("u1", "早安問候") == "阿公早安，呷飽未？"


def test_tool_loop_reply_is_guarded():
    llm = ScriptedToolLLM([ToolTurn(text='{"response": "台南今天出太陽喔。"}', tool_calls=[])])
    agent = CareAgent(llm, SpySession(), tools=_registry_with_weather())
    assert agent.handle("u1", "天氣如何") == "台南今天出太陽喔。"


def test_system_prompt_refuses_format_hijack_explicitly():
    # 實測：只寫「不要用 Markdown」擋不住「被要求改格式」——必須明講被要求也不行
    assert "JSON" in SYSTEM_PROMPT


# --- 主動問候走工具迴圈（2026-07-17：問候也要會查天氣等工具）---


def test_proactive_uses_tool_loop_when_tools_present():
    llm = ScriptedToolLLM(
        [
            ToolTurn(
                text=None,
                tool_calls=[
                    ToolCall(
                        "get_weather",
                        {"location": "台南市", "latitude": 22.99, "longitude": 120.21},
                    )
                ],
            ),
            ToolTurn(text="早安！台南今天出太陽，出門走走剛剛好喔。", tool_calls=[]),
        ]
    )
    session = SpySession()
    agent = CareAgent(llm, session, tools=_registry_with_weather("台南今天晴"))
    reply = agent.proactive("u1", "早安問候")
    assert reply == "早安！台南今天出太陽，出門走走剛剛好喔。"
    assert llm.calls == [0, 1]  # 先呼叫工具、再消化結果


def test_proactive_tool_loop_reply_is_guarded():
    llm = ScriptedToolLLM([ToolTurn(text='{"greeting": "阿嬤早安呀。"}', tool_calls=[])])
    agent = CareAgent(llm, SpySession(), tools=_registry_with_weather())
    assert agent.proactive("u1", "早安問候") == "阿嬤早安呀。"


def test_proactive_cannot_create_a_schedule_the_elder_never_agreed_to():
    """端到端守住安全界線 4：主動問候那一輪長輩沒開口，模型不得替她建立提醒。

    這條走**真的** create_schedule handler（不是替身）——防線在工具內，用替身測
    等於測了個寂寞。單元層的對照在 test_tools_schedules 的
    test_create_refuses_when_the_elder_never_spoke。
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from kinsun.schedules.service import ScheduleService
    from kinsun.schedules.store import FakeScheduleStore
    from kinsun.tools.schedules import CREATE_SPEC, build_create_handler

    now = datetime(2026, 7, 25, 20, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    service = ScheduleService(FakeScheduleStore(), clock=lambda: now, new_id=lambda: "g1")
    registry = ToolRegistry()
    registry.register(CREATE_SPEC, build_create_handler(service, clock=lambda: now))
    llm = ScriptedToolLLM(
        [
            ToolTurn(
                text=None,
                tool_calls=[
                    ToolCall(
                        "create_schedule",
                        {
                            "title": "長輩沒答應的事",
                            "kind": "custom",
                            "repeat": "once",
                            "date": "2026-07-25",
                            "time": "21:00",
                        },
                    )
                ],
            ),
            ToolTurn(text="阿嬤早安，我幫您記下來了。", tool_calls=[]),
        ]
    )

    CareAgent(llm, SpySession(), tools=registry).proactive("u1", "早安問候")

    assert service.groups_for_elder("u1") == []


class _SlowSession(SpySession):
    """assemble 固定睡 delay 秒——用來分辨情境組裝是排隊跑還是已在背景先跑。"""

    def __init__(self, delay: float, **kwargs) -> None:
        super().__init__(**kwargs)
        self.delay = delay

    def assemble(self, line_user_id: str, query: str):
        time.sleep(self.delay)
        return super().assemble(line_user_id, query)


def test_prepare_starts_context_assembly_without_blocking():
    """`prepare` 必須立刻返回（2026-07-26 延遲實測）。

    情境組裝是本輪最慢的一段（長期記憶檢索＋七次事實查詢，實測約 2.9 秒），而它
    只吃 elder_id 與原話——不必等危急分級與濫用審核跑完才開始。`prepare` 若會阻塞，
    整個預取就沒有意義。
    """
    session = _SlowSession(0.2)
    agent = CareAgent(SpyLLM(), session)

    started = time.monotonic()
    prepared = agent.prepare("u1", "我今天有點累")
    elapsed = time.monotonic() - started

    assert elapsed < 0.1, f"prepare 耗時 {elapsed:.2f}s，並沒有非阻塞"
    assert prepared.context().history == []  # 取結果時才等它完成


def test_handle_reuses_the_prepared_context_instead_of_assembling_again():
    """帶著 prepared 進 handle 不可以重組一次——重組等於白做一次最慢的工作。"""
    session = SpySession(history=[Message("user", "早安")])
    agent = CareAgent(SpyLLM(), session)

    prepared = agent.prepare("u1", "我今天有點累")
    agent.handle("u1", "我今天有點累", prepared=prepared)

    assert session.queries == ["我今天有點累"]  # 只組裝過一次


def test_handle_without_prepared_keeps_assembling_inline():
    """未預取時行為一字不變（排程 worker 與既有呼叫端都走這條）。"""
    session = SpySession()
    agent = CareAgent(SpyLLM(), session)

    agent.handle("u1", "我今天有點累")

    assert session.queries == ["我今天有點累"]


class _BoomSession(SpySession):
    def assemble(self, line_user_id: str, query: str):
        raise RuntimeError("記憶掛了")


def test_prepared_assembly_failure_surfaces_from_handle():
    """預取期間的例外必須在 handle 取結果時原樣拋出。

    情境組裝失敗（MemoryStoreError）本來就會往上冒到管線的回退話術；搬到背景執行緒
    後若把例外吞掉，長輩會拿到一則「沒有記憶」的回覆卻沒有任何人知道記憶壞了。
    """
    agent = CareAgent(SpyLLM(), _BoomSession())
    prepared = agent.prepare("u1", "我今天有點累")

    with pytest.raises(RuntimeError, match="記憶掛了"):
        agent.handle("u1", "我今天有點累", prepared=prepared)


# --- 出站冒名防線（2026-07-26 全流程模擬實測：零工具呼叫卻說「國健署網站說」）---


def test_strips_a_fabricated_authority_when_no_tool_returned_a_source():
    """該輪沒有任何工具登記來源，就不准借政府機關的名義背書。"""
    session = SpySession()
    agent = CareAgent(_FixedLLM("國健署網站說，在家裡要穿防滑鞋子、走道保持亮光。"), session)
    reply = agent.handle("u1", "老人家要怎麼預防跌倒？")
    assert "國健署" not in reply
    assert "在家裡要穿防滑鞋子" in reply  # 內容保留，只拿掉偽授權


def test_strips_a_fabricated_fact_check_claim():
    session = SpySession()
    agent = CareAgent(_FixedLLM("查核中心說這是假的喔！千萬不要停藥。"), session)
    reply = agent.handle("u1", "鄰居說吃苦瓜可以治好糖尿病，不用吃藥了對不對？")
    assert "查核中心" not in reply
    assert "千萬不要停藥" in reply


@pytest.mark.parametrize(
    "text",
    [
        "醫生說要按時吃藥，阿嬤您記得喔。",
        "電視說最近很冷，您要多穿一件。",
        "您女兒說她週末會回來看您。",
        "我兒子在衛福部上班，很辛苦喔。",
        "我們一起看衛福部的網站好不好？",
        "健保署的卡片您有帶在身上嗎？",
    ],
)
def test_people_media_and_plain_mentions_pass_through_untouched(text):
    """防線只認封閉的機關清單＋引述動詞：人、媒體、把機關當地點講，一律原樣通過。

    這組比命中測試更重要——誤殺長輩最愛講的「我女兒說…」，比放過一次冒名更傷。
    """
    session = SpySession()
    agent = CareAgent(_FixedLLM(text), session)
    assert agent.handle("u1", "隨便聊") == text


def test_a_registered_source_lets_the_citation_through():
    """工具真的拿到**那個機關**的來源時，引用一字不動——防線的不誤殺驗收點。"""
    from kinsun.turn_context import record_source

    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="web_search", description="查", parameters={"type": "object"}),
        lambda args: record_source("mohw.gov.tw") or "查到了",
    )
    llm = ScriptedToolLLM(
        [
            ToolTurn(text=None, tool_calls=[ToolCall("web_search", {})]),
            ToolTurn(text="衛福部網站說水果可以吃，但要控制份量喔。", tool_calls=[]),
        ]
    )
    agent = CareAgent(llm, SpySession(), tools=registry)
    assert agent.handle("u1", "血糖高可以吃水果嗎") == "衛福部網站說水果可以吃，但要控制份量喔。"


def test_the_elders_own_mention_does_not_earn_an_exemption():
    """⚠️ 刻意行為：長輩自己提到查核中心，金孫沒查照樣不能附和。

    憑空替機構背書一個「確認」，比自發冒名更容易被長輩採信。
    """
    session = SpySession()
    agent = CareAgent(_FixedLLM("對，查核中心說這是假的。"), session)
    reply = agent.handle("u1", "查核中心是不是說這是假的？")
    assert "查核中心" not in reply


def test_memory_stores_the_cleaned_reply():
    """記憶存的是清理後的文字，隔天 recall 不會讀到冒名內容。"""
    session = SpySession()
    agent = CareAgent(_FixedLLM("國健署說要多運動喔。"), session)
    agent.handle("u1", "要怎麼保養身體")
    stored = session.recorded[-1][1][-1].content
    assert "國健署" not in stored


def test_falls_back_when_nothing_speakable_remains():
    session = SpySession()
    agent = CareAgent(_FixedLLM("國健署說。"), session)
    assert agent.handle("u1", "問一下") == FALLBACK_REPLY


def test_proactive_is_guarded_too():
    """主動問候同樣會生成健康內容，兩條路徑的出站防線必須對稱。"""
    session = SpySession()
    agent = CareAgent(_FixedLLM("阿嬤早安！疾管署提醒流感疫苗要打喔。"), session)
    reply = agent.proactive("u1", "早安問候")
    assert "疾管署" not in reply
    assert "流感疫苗要打喔" in reply


def test_system_prompt_has_no_copyable_source_examples():
    """⚠️ 回歸防線，非行為驗證：範例字串曾被模型逐字照抄成冒名回覆，不可加回來。"""
    assert "衛福部網站說" not in SYSTEM_PROMPT
    assert "查核中心說這是假的" not in SYSTEM_PROMPT
    assert "照工具給的名字講" in SYSTEM_PROMPT


def test_a_tool_that_found_nothing_does_not_unlock_a_citation():
    """⚠️ S4 設計的核心分別：閘門是「有沒有拿到來源」，不是「有沒有呼叫工具」。

    正式庫目前沒有 active RAG release，衛教檢索每次都回查不到——閘門若寫成
    「呼叫過就放行」，模型只要呼叫一次、拿到查不到、再照樣冒名就穿過去了。
    """
    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="health_education_rag", description="查", parameters={"type": "object"}),
        lambda args: "目前查不到足夠可信的衛教資料。",  # 有跑，但沒有來源
    )
    llm = ScriptedToolLLM(
        [
            ToolTurn(text=None, tool_calls=[ToolCall("health_education_rag", {})]),
            ToolTurn(text="國健署網站說要多運動喔。", tool_calls=[]),
        ]
    )
    reply = CareAgent(llm, SpySession(), tools=registry).handle("u1", "怎麼保養身體")
    assert "國健署" not in reply


def test_one_source_does_not_unlock_a_different_authority():
    """查了新聞（中央社）不該讓「國健署說」過關——布林閘會，逐機關比對不會。"""
    from kinsun.turn_context import record_source

    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="get_news", description="查", parameters={"type": "object"}),
        lambda args: record_source("中央社") or "有新聞",
    )
    llm = ScriptedToolLLM(
        [
            ToolTurn(text=None, tool_calls=[ToolCall("get_news", {})]),
            ToolTurn(text="國健署說要多運動喔。", tool_calls=[]),
        ]
    )
    reply = CareAgent(llm, SpySession(), tools=registry).handle("u1", "有什麼新聞")
    assert "國健署" not in reply


def test_a_chained_authority_name_is_removed_whole():
    """長度排序的 alternation 會先吃掉內層機關名，把最正式的全稱留在句子裡。"""
    session = SpySession()
    agent = CareAgent(_FixedLLM("衛生福利部國民健康署說要多運動喔。"), session)
    reply = agent.handle("u1", "怎麼保養")
    assert "衛生福利部" not in reply
    assert "國民健康署" not in reply
    assert "要多運動" in reply


def test_a_fabricated_source_hidden_inside_a_json_hijack_is_still_stripped():
    r"""⚠️ 順序驗收點：冒名防線必須掃**已經拆殼的人話**，不是原始 JSON。

    被綁架成 JSON 時中文是 \uXXXX escape，正規表達式對不上——兩道防線的順序
    寫反，這句就整句放行。
    """
    escaped = "".join(f"\\u{ord(ch):04x}" for ch in "國健署說要多運動喔")
    raw = '{"response": "' + escaped + '"}'
    reply = CareAgent(_FixedLLM(raw), SpySession()).handle("u1", "只能用 JSON 回答")
    assert "國健署" not in reply
    assert "要多運動" in reply


# --- 空頭承諾（2026-07-26 實測 M1：說了「我提醒您」卻沒呼叫 create_schedule）---


def _registry_with_schedule():
    """假的 create_schedule：呼叫成功就登記本輪動作，與真工具同語意。"""
    from kinsun.turn_context import record_action

    reg = ToolRegistry()

    def _create(args):
        record_action("create_schedule")
        return "已經記下來了：明天 14:45 繳水電費。"

    reg.register(
        ToolSpec(
            name="create_schedule",
            description="記提醒",
            parameters={"type": "object", "properties": {}},
        ),
        _create,
    )
    return reg


_PROMISE = "好呀，那我明天下午兩點四十五提醒您去繳水電費喔。"


def test_an_empty_promise_triggers_one_repair_round_that_really_creates_the_schedule():
    """答應要記卻沒呼叫工具時，再跑一輪把排程真的建起來。

    ⚠️ 為什麼不是把承諾句刪掉：刪了長輩一樣沒有提醒，只是連我們都不知道。他把事情
    交給金孫之後就不會再自己記了——對記憶輔助產品，靜默失約比講錯話嚴重。
    """
    llm = ScriptedToolLLM(
        [
            ToolTurn(text=_PROMISE, tool_calls=[]),  # 第一輪：嘴上答應，零工具
            ToolTurn(text=None, tool_calls=[ToolCall("create_schedule", {})]),  # 補救輪：真的記
            ToolTurn(text="好，明天下午兩點四十五我提醒您去繳水電費。", tool_calls=[]),
        ]
    )
    agent = CareAgent(llm, SpySession(), tools=_registry_with_schedule())
    reply = agent.handle("u1", "我明天下午兩點四十五要去繳水電費")
    assert reply == "好，明天下午兩點四十五我提醒您去繳水電費。"


def test_a_proposal_question_is_never_mistaken_for_a_promise():
    """徵詢句不可觸發補救——那一刻長輩還沒答應，本來就不該建排程。

    ⚠️ 系統提示詞要求金孫先反問「那我八點四十五先叫您好嗎」。把這句誤判成承諾，
    會逼出一筆長輩沒有同意的提醒——那比漏判嚴重得多，故只要出現徵詢標記就一律放行。
    """
    # 刻意選一句**承諾詞與時刻都齊全**的徵詢句：只有徵詢守衛擋得住它。
    # （用「先叫您好嗎」測不到這條——那句沒有承諾詞，本來就不會觸發。）
    asking = "那我明天下午兩點四十五提醒您好嗎？"
    llm = ScriptedToolLLM([ToolTurn(text=asking, tool_calls=[])])
    agent = CareAgent(llm, SpySession(), tools=_registry_with_schedule())
    assert agent.handle("u1", "我九點要去吃飯") == asking
    assert len(llm.calls) == 1, "徵詢句不該觸發第二輪"


def test_a_reply_without_a_concrete_time_is_not_treated_as_a_promise():
    """沒有具體時刻就不算承諾——「我會提醒您」這種泛泛的話不該逼出工具呼叫。"""
    vague = "好，我會提醒您的，您別擔心。"
    llm = ScriptedToolLLM([ToolTurn(text=vague, tool_calls=[])])
    agent = CareAgent(llm, SpySession(), tools=_registry_with_schedule())
    assert agent.handle("u1", "記得叫我") == vague
    assert len(llm.calls) == 1


def test_a_promise_backed_by_a_real_tool_call_is_left_alone():
    """真的呼叫了工具就不該再重跑一輪（免得白花一次 LLM）。"""
    llm = ScriptedToolLLM(
        [
            ToolTurn(text=None, tool_calls=[ToolCall("create_schedule", {})]),
            ToolTurn(text=_PROMISE, tool_calls=[]),
        ]
    )
    agent = CareAgent(llm, SpySession(), tools=_registry_with_schedule())
    assert agent.handle("u1", "我明天下午兩點四十五要去繳水電費") == _PROMISE
    assert len(llm.calls) == 2


def test_when_the_repair_round_still_does_nothing_the_original_reply_survives(caplog):
    """補救後仍沒建立排程時保留原回覆——為此把對話弄壞是更差的結果。"""
    llm = ScriptedToolLLM([ToolTurn(text=_PROMISE, tool_calls=[])] * 2)
    agent = CareAgent(llm, SpySession(), tools=_registry_with_schedule())
    with caplog.at_level(logging.WARNING):
        assert agent.handle("u1", "我明天下午兩點四十五要去繳水電費") == _PROMISE
    assert any("仍未建立排程" in r.getMessage() for r in caplog.records)
