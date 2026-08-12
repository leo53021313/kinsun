// fx_art.js — 特效的造型資料
//   · 符號（愛心/星光/淚滴/怒氣/驚嘆/問號/Zzz/雪花/音符/思考點點）＝寫實霓虹燈
//   · 小生物（蜜蜂/蝴蝶/蜻蜓）＝可愛寫實
// 規格：upgrate/Knowledge Base/neon-critter-fx.md
//
// 霓虹的造型一律是**中心線**，不是輪廓也不是填色區：招牌是把一根固定口徑的
// 玻璃管折出形狀的，所以 fx.js 拿到 d 之後是用 stroke 疊出「遠場泛光 / 近場光暈 /
// 未點亮的玻璃 / 管 / 芯」五層。管徑（w）沿路徑不得變化——變寬變窄就穿幫了。
//
// 小生物的 SVG 直接寫在這裡（含漸層），因為它們要的是光影不是點陣；
// {U} 是每一隻自己的 id 前綴，由 fx.js 在建立元素時換掉，避免多隻共用漸層。
(function () {
  const PET = (window.PET = window.PET || {});

  // 霓虹調色盤：[遠場泛光, 管, 芯, 未點亮的玻璃]
  //   · 泛光保持色相，不可以往白色收（往白收就是「加了 glow 濾鏡」的樣子）
  //   · 芯是把色相推到接近白但留一點色
  //   · 玻璃是同色相的極深色。它同時解掉一個實務問題：熊的天空是淺藍的，
  //     純亮色霓虹在淺底上會糊掉，暗玻璃給了它輪廓。物理正確與可讀性同向。
  const NEON = {
    rose:   ["#ff1f63", "#ff2d6f", "#ffdbe8", "#48091f"],
    gold:   ["#ffab00", "#ffc21e", "#fff6d4", "#4a3200"],
    cyan:   ["#00bfff", "#2ad4ff", "#ddf8ff", "#062f42"],
    red:    ["#ff1e10", "#ff3b30", "#ffdfd9", "#4a0d07"],
    flame:  ["#ff3d00", "#ff5f26", "#ffe6d4", "#4a1400"],
    violet: ["#7c3cff", "#9b6bff", "#eee3ff", "#25084f"],
    ice:    ["#3d7dff", "#6ea8ff", "#e4efff", "#0d1f4a"],
    frost:  ["#35c6ff", "#8fe6ff", "#f4ffff", "#0c3346"],
    mint:   ["#00c76a", "#39e08b", "#e0ffee", "#04361f"],
    amber:  ["#ff9500", "#ffb347", "#fff2da", "#4a2a00"],
  };

  // 每個符號一到三組 {c, w, d}。同色同管徑的筆畫合併成一條 d（多段 M），
  // 這樣不管形狀多複雜（雪花有 9 段），每組都只付 5 個 <path> 的代價。
  const SYM = {
    // 一條彎成愛心的管，不是一塊填色
    heart: [{ c: "rose", w: 4.8, d:
      "M0 -13 C-8 -26 -30 -21 -30 -4 C-30 12 -11 20 0 30 " +
      "C11 20 30 12 30 -4 C30 -21 8 -26 0 -13 Z" }],
    // 四角星：邊是凹的，才不會讀成菱形
    sparkle: [{ c: "gold", w: 4.4, d:
      "M0 -30 Q3.5 -8 24 0 Q3.5 8 0 30 Q-3.5 8 -24 0 Q-3.5 -8 0 -30 Z" }],
    drop: [{ c: "cyan", w: 4.6, d:
      "M0 -26 C11 -9 20.5 2 20.5 10.5 A21 21 0 1 1 -20.5 10.5 C-20.5 2 -11 -9 0 -26 Z" }],
    // 怒氣：四個直角折彎圍成一個中空的十字，這就是 💢。
    // 原本是三條斜槓，折成管之後讀起來是「X 再加一撇」，不是生氣。
    anger: [{ c: "red", w: 5, d:
      "M-22 -7 L-7 -7 L-7 -22 M7 -22 L7 -7 L22 -7 " +
      "M22 7 L7 7 L7 22 M-7 22 L-7 7 L-22 7" }],
    // 「!」與「?」的那一點就是一小段同管徑的管——真的招牌就是這樣做的
    bang: [{ c: "flame", w: 5.2, d: "M0 -30 L0 5 M0 21 L0 21.4" }],
    quest: [{ c: "violet", w: 4.8, d:
      "M-16 -17 C-16 -33 16 -33 16 -15 C16 -3 1 -1 1 12 M1 22 L1 22.4" }],
    // Z 折成一條連續的管（招牌就是這樣折的），不是三段拼起來
    zzz: [{ c: "ice", w: 4.6, d: "M-15 -16 L15 -16 L-15 14 L15 14" }],
    // 雪花：三條主軸 + 六個倒鉤，全部併進同一條 d。
    // 倒鉤的頂點必須**落在軸上**、開口朝外（V 字），這是真雪花分枝的樣子；
    // 頂點放在軸外會變成一堆朝內的箭頭，整朵就散了。
    flake: [{ c: "frost", w: 3.6, d:
      "M0 -22 L0 22 M-19 -11 L19 11 M-19 11 L19 -11 " +
      "M4.59 -20.19 L0 -13.64 L-4.59 -20.19 M4.59 20.19 L0 13.64 L-4.59 20.19 " +
      "M15.16 14.08 L11.78 6.82 L19.76 6.12 M19.76 -6.12 L11.78 -6.82 L15.16 -14.08 " +
      "M-19.76 6.12 L-11.78 6.82 L-15.16 14.08 M-15.16 -14.08 L-11.78 -6.82 L-19.76 -6.12" }],
    note: [{ c: "mint", w: 4.4, d:
      "M4 10 C4 2 -8 0 -14 7 C-20 14 -15 22 -7 20 C0 18.5 4 15 4 10 Z " +
      "M4 10 L4 -24 C15 -20 20 -12 16 -3" }],
    // 思考點點：三段零長度的管（圓帽 = 一個點），管徑遞增就是說話的節奏。
    // 這是招牌上打點的做法，不是三個填色圓。
    // 管徑就是點的直徑，光暈也跟著管徑放大，所以點不能做太大——
    // 8.5/11/13.5 的三顆會各自帶一圈 60 單位的暈，糊成一團橘雲。
    // 對齊「!」「?」那一點的尺度（5 左右）才讀得出是三顆燈。
    dots: [
      { c: "amber", w: 6, d: "M-19 1 L-19 1.4" },
      { c: "amber", w: 7.6, d: "M0 -1 L0 -0.6" },
      { c: "amber", w: 9.2, d: "M20 -4 L20 -3.6" },
    ],
  };

  // ---------- 可愛寫實的小生物 ----------
  // 可愛來自比例（頭大、眼大、屁股圓），寫實來自光（漸層、高光、遮蔽、透光）。
  // 平塗 + 大眼睛只會得到貼圖，所以這裡沒有任何一塊是純色平塗的。
  const CRITTER = {
    // 蜜蜂：頭在左的俯視。胸節要有絨毛邊，腹部的條紋要順著肚子的弧度彎。
    bee: {
      defs:
        '<radialGradient id="{U}ab" cx=".34" cy=".26" r=".82">' +
        '<stop offset="0" stop-color="#ffe9a8"/><stop offset=".42" stop-color="#f7c341"/>' +
        '<stop offset=".82" stop-color="#dc9a17"/><stop offset="1" stop-color="#a86f0c"/>' +
        "</radialGradient>" +
        '<radialGradient id="{U}th" cx=".32" cy=".26" r=".85">' +
        '<stop offset="0" stop-color="#b98a4e"/><stop offset=".55" stop-color="#8a5f2c"/>' +
        '<stop offset="1" stop-color="#4e3315"/></radialGradient>' +
        '<radialGradient id="{U}hd" cx=".34" cy=".3" r=".8">' +
        '<stop offset="0" stop-color="#6b5330"/><stop offset="1" stop-color="#2a1d0c"/>' +
        "</radialGradient>" +
        '<linearGradient id="{U}wg" x1=".1" y1="1" x2=".9" y2="0">' +
        '<stop offset="0" stop-color="#f2faff" stop-opacity=".86"/>' +
        '<stop offset=".55" stop-color="#cfe6f5" stop-opacity=".62"/>' +
        '<stop offset="1" stop-color="#ffffff" stop-opacity=".3"/></linearGradient>' +
        // 條紋要被肚子裁掉，才會看起來是「繞在肚子上」而不是壓在上面
        '<clipPath id="{U}cl"><ellipse cx="5" cy="4" rx="17" ry="13"/></clipPath>',
      wingL:
        '<path d="M-6 -7 C-15 -22 -31 -24 -32 -13 C-33 -4 -17 -1 -6 -7 Z" fill="url(#{U}wg)"/>' +
        '<g fill="none" stroke="#9fc4dc" stroke-opacity=".42" stroke-width=".8">' +
        '<path d="M-7 -8 C-16 -15 -25 -18 -30 -14"/>' +
        '<path d="M-7 -7 C-17 -11 -25 -12 -30 -11"/></g>',
      wingR:
        '<path d="M-2 -7 C4 -23 20 -26 23 -15 C25 -6 8 -2 -2 -7 Z" fill="url(#{U}wg)"/>' +
        '<g fill="none" stroke="#9fc4dc" stroke-opacity=".42" stroke-width=".8">' +
        '<path d="M-1 -8 C6 -16 15 -20 21 -16"/>' +
        '<path d="M-1 -7 C7 -12 15 -14 21 -13"/></g>',
      body:
        // 腹部
        '<ellipse cx="5" cy="4" rx="17" ry="13" fill="url(#{U}ab)"/>' +
        // 條紋：彎的，而且被腹部裁掉
        '<g clip-path="url(#{U}cl)" fill="none" stroke="#3b2a10" stroke-opacity=".88" ' +
        'stroke-linecap="round">' +
        '<path d="M-3 -10 Q0 4 -3 18" stroke-width="4.6"/>' +
        '<path d="M6 -12 Q9.5 4 6 20" stroke-width="5"/>' +
        '<path d="M15 -10 Q18 4 15 18" stroke-width="4.4"/></g>' +
        // 腹部前緣一點反光（幾丁質是有光澤的）
        '<ellipse cx="0" cy="-2" rx="6" ry="3.4" fill="#fff6d0" fill-opacity=".34" ' +
        'transform="rotate(-18 0 -2)"/>' +
        // 胸節的絨毛：外緣一圈毛邊，沒有它蜜蜂會變成光滑的塑膠橢圓
        '<g fill="none" stroke="#c79a5c" stroke-opacity=".75" stroke-width="1.5" ' +
        'stroke-linecap="round">' +
        '<path d="M-11 -9 L-12 -14"/><path d="M-6 -10 L-6 -15"/><path d="M-15 -7 L-18 -11"/>' +
        '<path d="M-18 -2 L-23 -4"/><path d="M-18 4 L-23 6"/><path d="M-15 9 L-18 13"/>' +
        '<path d="M-10 11 L-11 16"/><path d="M-5 11 L-4 16"/></g>' +
        '<ellipse cx="-11" cy="1" rx="9.5" ry="10.5" fill="url(#{U}th)"/>' +
        '<ellipse cx="-14" cy="-4" rx="4" ry="2.6" fill="#e2bd82" fill-opacity=".4" ' +
        'transform="rotate(-28 -14 -4)"/>' +
        // 頭：放大一點，這是可愛的來源
        '<circle cx="-22" cy="0" r="8" fill="url(#{U}hd)"/>' +
        '<ellipse cx="-25" cy="-1.5" rx="3.4" ry="4.4" fill="#14100a"/>' +
        '<ellipse cx="-20" cy="-2.5" rx="2.6" ry="3.4" fill="#14100a" fill-opacity=".82"/>' +
        '<circle cx="-26.2" cy="-3.2" r="1.35" fill="#ffffff" fill-opacity=".92"/>' +
        '<circle cx="-20.8" cy="-3.8" r="1" fill="#ffffff" fill-opacity=".78"/>' +
        // 觸角：末端帶勾
        '<g fill="none" stroke="#2a1d0c" stroke-width="1.6" stroke-linecap="round">' +
        '<path d="M-25 -6 C-29 -12 -32 -14 -35 -13"/>' +
        '<path d="M-20 -7 C-22 -14 -24 -17 -27 -17"/></g>' +
        '<circle cx="-35.4" cy="-12.8" r="1.5" fill="#2a1d0c"/>' +
        '<circle cx="-27.4" cy="-17.2" r="1.5" fill="#2a1d0c"/>' +
        // 腳
        '<g fill="none" stroke="#3b2a10" stroke-opacity=".8" stroke-width="1.4" ' +
        'stroke-linecap="round">' +
        '<path d="M-9 11 C-9 16 -12 18 -15 18"/><path d="M-1 14 C-1 19 -3 21 -6 21"/>' +
        '<path d="M7 15 C8 19 7 21 4 22"/></g>',
    },

    // 蝴蝶：頭在上的俯視。翅脈由翅根放射、外緣一條深色鑲邊、後翅小且偏下。
    bfly: {
      defs:
        '<linearGradient id="{U}fw" x1=".95" y1=".1" x2=".1" y2=".9">' +
        '<stop offset="0" stop-color="#ffd9ea"/><stop offset=".38" stop-color="#ff9dc6"/>' +
        '<stop offset=".78" stop-color="#ef6ba6"/><stop offset="1" stop-color="#c9427f"/>' +
        "</linearGradient>" +
        '<linearGradient id="{U}hw" x1=".9" y1="0" x2=".2" y2="1">' +
        '<stop offset="0" stop-color="#ff9dc6"/><stop offset=".6" stop-color="#e86ba8"/>' +
        '<stop offset="1" stop-color="#b83a78"/></linearGradient>' +
        '<linearGradient id="{U}bd" x1="0" y1="0" x2="1" y2="0">' +
        '<stop offset="0" stop-color="#2e2028"/><stop offset=".34" stop-color="#6b5260"/>' +
        '<stop offset=".72" stop-color="#43323c"/><stop offset="1" stop-color="#241a20"/>' +
        "</linearGradient>",
      wingL:
        '<g opacity=".92">' +
        '<path d="M-2 -3 C-13 -23 -32 -25 -35 -11 C-37 1 -20 8 -3 2 Z" fill="url(#{U}fw)" ' +
        'stroke="#8e2a5c" stroke-opacity=".62" stroke-width="2.6" stroke-linejoin="round"/>' +
        '<path d="M-2 3 C-12 8 -23 17 -21 26 C-19 34 -6 27 -1 11 Z" fill="url(#{U}hw)" ' +
        'stroke="#8e2a5c" stroke-opacity=".62" stroke-width="2.4" stroke-linejoin="round"/>' +
        '<g fill="none" stroke="#7d2450" stroke-opacity=".34" stroke-width=".9">' +
        '<path d="M-3 -2 C-14 -8 -24 -13 -31 -13"/><path d="M-3 -1 C-15 -3 -25 -5 -32 -6"/>' +
        '<path d="M-3 0 C-14 3 -22 4 -28 2"/><path d="M-3 5 C-9 11 -15 18 -18 25"/>' +
        '<path d="M-2 6 C-6 13 -8 20 -8 25"/></g>' +
        '<ellipse cx="-26" cy="-9" rx="3.6" ry="2.8" fill="#fff2f8" fill-opacity=".72" ' +
        'transform="rotate(-24 -26 -9)"/>' +
        '<ellipse cx="-18" cy="-13" rx="2.4" ry="1.9" fill="#fff2f8" fill-opacity=".6"/>' +
        '<ellipse cx="-14" cy="22" rx="2.4" ry="2" fill="#fff2f8" fill-opacity=".58" ' +
        'transform="rotate(38 -14 22)"/></g>',
      wingR:
        '<g opacity=".92">' +
        '<path d="M2 -3 C13 -23 32 -25 35 -11 C37 1 20 8 3 2 Z" fill="url(#{U}fw)" ' +
        'stroke="#8e2a5c" stroke-opacity=".62" stroke-width="2.6" stroke-linejoin="round"/>' +
        '<path d="M2 3 C12 8 23 17 21 26 C19 34 6 27 1 11 Z" fill="url(#{U}hw)" ' +
        'stroke="#8e2a5c" stroke-opacity=".62" stroke-width="2.4" stroke-linejoin="round"/>' +
        '<g fill="none" stroke="#7d2450" stroke-opacity=".34" stroke-width=".9">' +
        '<path d="M3 -2 C14 -8 24 -13 31 -13"/><path d="M3 -1 C15 -3 25 -5 32 -6"/>' +
        '<path d="M3 0 C14 3 22 4 28 2"/><path d="M3 5 C9 11 15 18 18 25"/>' +
        '<path d="M2 6 C6 13 8 20 8 25"/></g>' +
        '<ellipse cx="26" cy="-9" rx="3.6" ry="2.8" fill="#fff2f8" fill-opacity=".72" ' +
        'transform="rotate(24 26 -9)"/>' +
        '<ellipse cx="18" cy="-13" rx="2.4" ry="1.9" fill="#fff2f8" fill-opacity=".6"/>' +
        '<ellipse cx="14" cy="22" rx="2.4" ry="2" fill="#fff2f8" fill-opacity=".58" ' +
        'transform="rotate(-38 14 22)"/></g>',
      body:
        // 腹部：分節、末端收細
        '<path d="M-3.2 -2 C-3.6 8 -2.6 15 0 18 C2.6 15 3.6 8 3.2 -2 Z" fill="url(#{U}bd)"/>' +
        '<g fill="none" stroke="#1b1218" stroke-opacity=".5" stroke-width=".9">' +
        '<path d="M-3.3 2 L3.3 2"/><path d="M-3.1 6 L3.1 6"/><path d="M-2.6 10 L2.6 10"/>' +
        '<path d="M-1.8 14 L1.8 14"/></g>' +
        // 胸節：毛茸茸
        '<ellipse cx="0" cy="-5" rx="4.6" ry="7" fill="url(#{U}bd)"/>' +
        '<g fill="none" stroke="#8b7280" stroke-opacity=".7" stroke-width="1.2" ' +
        'stroke-linecap="round">' +
        '<path d="M-4 -9 L-6.5 -12"/><path d="M0 -11 L0 -14"/><path d="M4 -9 L6.5 -12"/>' +
        '<path d="M-5 -4 L-8 -5"/><path d="M5 -4 L8 -5"/></g>' +
        '<ellipse cx="-1.4" cy="-7" rx="1.4" ry="3.4" fill="#b9a3b0" fill-opacity=".55"/>' +
        // 頭與大眼睛
        '<circle cx="0" cy="-13" r="4.6" fill="#2b1e26"/>' +
        '<circle cx="-2.1" cy="-13.6" r="2.5" fill="#0d090c"/>' +
        '<circle cx="2.1" cy="-13.6" r="2.5" fill="#0d090c"/>' +
        '<circle cx="-2.8" cy="-14.6" r="1" fill="#ffffff" fill-opacity=".9"/>' +
        '<circle cx="1.4" cy="-14.6" r=".8" fill="#ffffff" fill-opacity=".78"/>' +
        // 觸角：末端棒狀
        '<g fill="none" stroke="#241a20" stroke-width="1.5" stroke-linecap="round">' +
        '<path d="M-2 -16 C-6 -22 -10 -25 -13 -25"/>' +
        '<path d="M2 -16 C6 -22 10 -25 13 -25"/></g>' +
        '<ellipse cx="-13.6" cy="-25" rx="2.2" ry="1.5" fill="#241a20" ' +
        'transform="rotate(-14 -13.6 -25)"/>' +
        '<ellipse cx="13.6" cy="-25" rx="2.2" ry="1.5" fill="#241a20" ' +
        'transform="rotate(14 13.6 -25)"/>',
    },

    // 蜻蜓：頭在上的俯視。兩顆巨大的複眼在頭頂相接是它的定義性特徵，
    // 翅膀近全透明的脈網、前緣近翅尖要有翅痣。
    dfly: {
      defs:
        '<linearGradient id="{U}ab" x1="0" y1="0" x2="1" y2="0">' +
        '<stop offset="0" stop-color="#1d5e6e"/><stop offset=".3" stop-color="#4fb6cc"/>' +
        '<stop offset=".6" stop-color="#2d8ba1"/><stop offset="1" stop-color="#15414c"/>' +
        "</linearGradient>" +
        '<radialGradient id="{U}tx" cx=".32" cy=".26" r=".85">' +
        '<stop offset="0" stop-color="#8ce4f2"/><stop offset=".5" stop-color="#3fa6bd"/>' +
        '<stop offset="1" stop-color="#175867"/></radialGradient>' +
        '<radialGradient id="{U}ey" cx=".3" cy=".24" r=".85">' +
        '<stop offset="0" stop-color="#a7ecf7"/><stop offset=".42" stop-color="#41b3c9"/>' +
        '<stop offset=".82" stop-color="#1c6b7d"/><stop offset="1" stop-color="#0d3a45"/>' +
        "</radialGradient>",
      // 膜幾乎全透明、脈網才是看得見的東西——真的蜻蜓翅膀就是這樣，
      // 而且這比「整片半透明」更好解：整片壓到 0.42 會連脈一起淡掉，
      // 在淺藍天空下就整片消失。
      wingL:
        '<path d="M-3 -5 C-16 -13 -34 -13 -40 -5 C-43 1 -25 5 -4 -1 Z" fill="#e8f6fd" ' +
        'fill-opacity=".3"/>' +
        '<path d="M-3 4 C-15 -1 -31 0 -36 7 C-38 12 -22 13 -4 8 Z" fill="#e8f6fd" ' +
        'fill-opacity=".3"/>' +
        '<g fill="none" stroke="#4d7f97" stroke-opacity=".6" stroke-width=".6">' +
        '<path d="M-4 -4 C-17 -9 -30 -10 -38 -5"/><path d="M-4 -2 C-18 -4 -30 -4 -38 -3"/>' +
        '<path d="M-12 -8 L-13 -1"/><path d="M-20 -10 L-21 -2"/><path d="M-28 -10 L-29 -3"/>' +
        '<path d="M-4 5 C-16 2 -28 3 -34 8"/><path d="M-11 1 L-12 8"/>' +
        '<path d="M-19 1 L-20 9"/><path d="M-27 3 L-28 10"/></g>' +
        // 翅痣：前緣近翅尖那一塊深色的細胞
        '<rect x="-36" y="-10.5" width="6.5" height="2.6" rx="1.2" fill="#33637a" ' +
        'fill-opacity=".85" transform="rotate(-8 -33 -9)"/>',
      wingR:
        '<path d="M3 -5 C16 -13 34 -13 40 -5 C43 1 25 5 4 -1 Z" fill="#e8f6fd" ' +
        'fill-opacity=".3"/>' +
        '<path d="M3 4 C15 -1 31 0 36 7 C38 12 22 13 4 8 Z" fill="#e8f6fd" ' +
        'fill-opacity=".3"/>' +
        '<g fill="none" stroke="#4d7f97" stroke-opacity=".6" stroke-width=".6">' +
        '<path d="M4 -4 C17 -9 30 -10 38 -5"/><path d="M4 -2 C18 -4 30 -4 38 -3"/>' +
        '<path d="M12 -8 L13 -1"/><path d="M20 -10 L21 -2"/><path d="M28 -10 L29 -3"/>' +
        '<path d="M4 5 C16 2 28 3 34 8"/><path d="M11 1 L12 8"/>' +
        '<path d="M19 1 L20 9"/><path d="M27 3 L28 10"/></g>' +
        '<rect x="29.5" y="-10.5" width="6.5" height="2.6" rx="1.2" fill="#33637a" ' +
        'fill-opacity=".85" transform="rotate(8 33 -9)"/>',
      body:
        // 腹部：細長、分節、往末端收
        '<path d="M-3.4 0 C-3.8 12 -2.6 24 -1.4 33 L1.4 33 C2.6 24 3.8 12 3.4 0 Z" ' +
        'fill="url(#{U}ab)"/>' +
        '<g fill="none" stroke="#0e3a45" stroke-opacity=".45" stroke-width=".85">' +
        '<path d="M-3.6 5 L3.6 5"/><path d="M-3.5 10 L3.5 10"/><path d="M-3.2 15 L3.2 15"/>' +
        '<path d="M-2.9 20 L2.9 20"/><path d="M-2.5 25 L2.5 25"/><path d="M-2 29 L2 29"/></g>' +
        '<path d="M-1.2 2 C-1.6 12 -1 22 -0.4 30" fill="none" stroke="#bff0fa" ' +
        'stroke-opacity=".45" stroke-width="1.1"/>' +
        // 胸節：要明顯小於複眼，否則它會被讀成第二顆頭
        '<ellipse cx="0" cy="-2" rx="5.6" ry="7" fill="url(#{U}tx)"/>' +
        '<ellipse cx="-1.8" cy="-5" rx="1.8" ry="3.2" fill="#d8f6ff" fill-opacity=".5" ' +
        'transform="rotate(-16 -1.8 -5)"/>' +
        // 複眼：全身最大的部位，而且在頭頂相接。這是蜻蜓的定義性特徵，
        // 也剛好是「可愛」的來源，所以刻意做到比胸節大。
        '<ellipse cx="-5" cy="-15" rx="7.2" ry="6.4" fill="url(#{U}ey)"/>' +
        '<ellipse cx="5" cy="-15" rx="7.2" ry="6.4" fill="url(#{U}ey)"/>' +
        // 兩眼相接處要有一條縫，不然後畫的那顆會整個蓋掉前一顆
        '<path d="M0 -20.6 C-.6 -17 -.6 -13 0 -9.2" fill="none" stroke="#0d3a45" ' +
        'stroke-opacity=".55" stroke-width="1.1" stroke-linecap="round"/>' +
        '<circle cx="-7.4" cy="-17.4" r="2" fill="#ffffff" fill-opacity=".9"/>' +
        '<circle cx="2.6" cy="-17.4" r="1.6" fill="#ffffff" fill-opacity=".78"/>' +
        '<circle cx="-3.4" cy="-12.4" r="1" fill="#ffffff" fill-opacity=".38"/>' +
        // 腳：收在胸下（飛行中的蜻蜓是把腳收成籃子的）
        '<g fill="none" stroke="#124c5a" stroke-opacity=".8" stroke-width="1.2" ' +
        'stroke-linecap="round">' +
        '<path d="M-5 -6 C-9 -3 -10 1 -8 3"/><path d="M5 -6 C9 -3 10 1 8 3"/>' +
        '<path d="M-4 1 C-7 3 -7 6 -5 7"/><path d="M4 1 C7 3 7 6 5 7"/></g>',
    },
  };

  PET.FX_ART = { version: "neon-critter-v013", neon: NEON, sym: SYM, critter: CRITTER };
})();
