"""阿白臉上的表情詞彙——LLM 挑表情時的合法值域。

⚠️ **這份清單不是後端自己定的**，是角色 renderer（`shared/otto-pet-core/emotions.js`）
真的畫得出來的 50 種表情。挑到清單外的字，renderer 會整個忽略、阿白就不動表情
——而那不會有任何錯誤訊息。`tests/test_emotions.py` 逐字比對兩邊，漂掉就紅。

⚠️ `BLOCKED` 同樣鏡射 renderer 的 `sentiment.js::BLOCKED_EMOTIONS`（接手指示第 10 條，
CRITICAL）：阿白可以同理長輩的不舒服，但不能對長輩生氣、不耐、嫌惡、猜忌或驚慌。
renderer 內另有一道同樣的防線——這裡先擋是**不讓它離開後端**，而不是取代那一道。
"""

from __future__ import annotations

#: 依 renderer 的分組排列，方便和 `emotions.js` 對照。
AVATAR_EMOTIONS: tuple[str, ...] = (
    # 正向
    "happy",
    "excited",
    "laughing",
    "celebrating",
    "playful",
    "mischief",
    "proud",
    "determined",
    # 柔和
    "calm",
    "relaxed",
    "relieved",
    "grateful",
    "touched",
    "love",
    "admiring",
    "hopeful",
    "apologetic",
    # 低落
    "sad",
    "crying",
    "disappointed",
    "hurt",
    "lonely",
    "guilty",
    "bored",
    "sulking",
    # 高張力
    "angry",
    "furious",
    "annoyed",
    "jealous",
    "disgusted",
    "suspicious",
    # 驚嚇
    "surprised",
    "shocked",
    "scared",
    "panic",
    "nervous",
    "embarrassed",
    "dizzy",
    # 思考
    "confused",
    "thinking",
    "curious",
    # 生理
    "sleepy",
    "exhausted",
    "hungry",
    "cold",
    "hot",
    "sick",
    # 社交
    "shy",
    "greeting",
    "agreeing",
)

#: 阿白不會對長輩表現出來的表情（與 renderer 的 BLOCKED_EMOTIONS 同一份）。
BLOCKED_EMOTIONS: frozenset[str] = frozenset(
    {
        # 對長輩本人的負面情緒
        "angry",
        "furious",
        "annoyed",
        "disgusted",
        "jealous",
        "suspicious",
        "bored",
        "sulking",
        # 會嚇到人：長輩說胸口悶時要沉穩，慌張交給家屬端危急通知
        "panic",
        "shocked",
        "scared",
    }
)

#: 挑不出來、或挑到不該用的，一律退回這一個。
FALLBACK_EMOTION = "calm"

#: LLM 可以挑的值域＝畫得出來的減掉不該用的。
#:
#: ⚠️ **黑名單情緒直接不進 enum**，而不是「讓它挑了再擋掉」：值域是模型唯一看得到的
#: 規則，能挑到的東西就是它會挑的東西。提示詞另有一條規則，兩者是同一件事的兩道保險。
SELECTABLE_EMOTIONS: tuple[str, ...] = tuple(
    emotion for emotion in AVATAR_EMOTIONS if emotion not in BLOCKED_EMOTIONS
)


def sanitize_emotion(emotion: str | None) -> str:
    """把 LLM 給的表情收成一定畫得出來、且一定不傷人的值。

    空字串、清單外的字、黑名單情緒，一律回 `calm`——寧可平靜也不要挑錯。
    """
    if not emotion:
        return FALLBACK_EMOTION
    key = emotion.strip()
    if key not in AVATAR_EMOTIONS or key in BLOCKED_EMOTIONS:
        return FALLBACK_EMOTION
    return key
