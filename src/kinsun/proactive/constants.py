"""主動關懷的共用常數。

⚠️ **本檔不得 import 任何 kinsun 模組**——它同時被 config（全庫最低層）與領域模組
引用，一旦有相依就會把整條相依鏈拖進 config，並開啟循環匯入的可能。

本檔的存在有實測理由：SLOT_MINUTES 原本住在 greeting_time，config 為了取用它而
import greeting_time，於是沿著 greeting_time → memory.shortterm → db 把 psycopg
（90＋子模組）與連線池全拉進了最低層。回歸測試見
tests/test_config.py::test_importing_config_does_not_pull_in_the_database_driver。
"""

from __future__ import annotations

# 問候 job 每半小時掃描一次（cron `0,30 * * * *`，見 proactive/jobs.py 的
# GREETING_SCAN_CRON），故偏好時間必須落在整點或半點——存 07:45 卻在 08:00 問候，
# 是對後台說謊。這是「掃描間隔」這件事的唯一真實來源：greeting_time 用它對齊時間
# （_align），config 用它驗證 PROACTIVE_GREETING_MAX_SHIFT_MINUTES 是其正倍數。
# 任何一方自己寫死 30，兩份真相就會漂移。
SLOT_MINUTES = 30
