# ── 第1行：載入內建模組 ──────────────────────────────────────
import os          # 讓 Python 讀取電腦的環境變數（例如 API 金鑰）
import json        # 把 API 回傳的 JSON 格式資料轉換成 Python 可以用的字典

# ── 第2行：載入外部套件 ──────────────────────────────────────
import requests                         # 發送 HTTP 請求到各個 API
from google import genai      # 連接 google AI
from google.genai import types
from dotenv import load_dotenv          # 讀取 .env 檔案裡的金鑰

# ── 讀取 .env 裡的金鑰 ───────────────────────────────────────
load_dotenv()   # 執行後，.env 裡的內容就會被載入成環境變數

# 從環境變數取出金鑰，存成 Python 變數
GEMINI_KEY        = os.getenv("GEMINI_API_KEY")
TDX_CLIENT_ID     = os.getenv("TDX_CLIENT_ID")
TDX_CLIENT_SECRET = os.getenv("TDX_CLIENT_SECRET")

def get_tdx_token() -> str:
    """向 TDX 換取臨時通行證"""
    url = "https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token"
    response = requests.post(url, data={
        "grant_type":    "client_credentials",
        "client_id":     TDX_CLIENT_ID,
        "client_secret": TDX_CLIENT_SECRET
    })
    return response.json().get("access_token", "")

# ── 建立 Claude 的連線物件 ───────────────────────────────────
client = genai.Client(api_key=GEMINI_KEY)
# 建立客戶端物件，之後用這個來發送請求


# ════════════════════════════════════════════════════════════
#  工具函式：每個函式負責呼叫一個 API
# ════════════════════════════════════════════════════════════

def get_google_route(origin: str, destination: str) -> dict:
    """
    使用 OSRM 免費路線 API（不需要任何金鑰）
    先用 Nominatim 把地名轉成經緯度，再用 OSRM 計算路線
    """
    
    # 第一步：把地名轉成經緯度（用 OpenStreetMap 的 Nominatim）
    def get_coordinates(place_name: str):
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": place_name + " 台灣",  # 加上台灣避免找到其他國家
            "format": "json",
            "limit": 1
        }
        headers = {"User-Agent": "TransportAgent/1.0"}  # Nominatim 要求加這個
        res = requests.get(url, params=params, headers=headers)
        data = res.json()
        if data:
            return float(data[0]["lon"]), float(data[0]["lat"])  # 回傳經度、緯度
        return None, None
    
    # 取得出發地和目的地的經緯度
    origin_lon, origin_lat = get_coordinates(origin)
    dest_lon, dest_lat     = get_coordinates(destination)
    
    if not origin_lat or not dest_lat:
        return {"錯誤": "找不到地點座標，請換個地名試試"}
    
    # 第二步：用 OSRM 計算路線
    url = (
        f"http://router.project-osrm.org/route/v1/driving/"
        f"{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
        f"?overview=false"
    )
    res = requests.get(url, timeout=10)
    data = res.json()
    
    if data.get("code") == "Ok":
        route = data["routes"][0]
        distance_km = round(route["distance"] / 1000, 1)  # 公尺換成公里
        duration_min = round(route["duration"] / 60, 0)   # 秒換成分鐘
        return {
            "出發地": origin,
            "目的地": destination,
            "距離": f"{distance_km} 公里",
            "開車時間": f"{int(duration_min)} 分鐘",
        }
    
    return {"錯誤": "路線計算失敗"}


def get_taipei_bus(route_name: str) -> dict:
    """
    呼叫台北市政府公車 API（TDC 平台，免費、免帳號）。
    route_name = 公車路線名稱（例如 "307"、"信義幹線"）
    回傳值：包含到站預估時間的字典
    """
    # PTX 平台的公車即時資料 API（台北市）
    url = (
        f"https://tdx.transportdata.tw/api/basic/v2/Bus/RealTimeNearStop/City/Taipei?%24top=30&%24format=JSON"
    )
    # PTX 平台不需要帳號，但要加這個 Header 才不會被擋
    headers = {
    "Accept": "application/json",
    "Authorization": f"Bearer {get_tdx_token()}"
}
    
    response = requests.get(url, headers=headers)  # 發送請求
    
    if response.status_code == 200:     # 200 代表請求成功
        data = response.json()          # 解析 JSON
        results = []
        for item in data[:3]:           # 只取前 3 筆，避免資料太多
            eta = item.get("EstimatedTime")        # 取出秒數
    if eta is not None:
        minutes = round(eta / 60)          # 秒換算成分鐘
        eta_text = f"約 {minutes} 分鐘後"
    else:
        eta_text = "即將到站或無資料"

    results.append({
    "站名":     item.get("StopName", {}).get("Zh_tw", "未知"),
    "預計到站": eta_text               # ← 換成這個
})
    return {"公車路線": route_name, "到站資訊": results}
    
    return {"錯誤": f"無法取得 {route_name} 路線資料"}


def get_taipei_mrt(station_name: str) -> dict:
    """
    呼叫台北捷運 API（同樣來自 TDC 平台）。
    station_name = 捷運站名（例如 "台北車站"、"信義安和"）
    回傳值：包含捷運班次資訊的字典
    """
    url = (
        f"https://tdx.transportdata.tw/api/basic/v2/Rail/Metro/StationOfRoute/TRTC?%24top=30&%24format=JSON"
        # TRTC = 台北捷運英文縮寫
    )
    headers = {
    "Accept": "application/json",
    "Authorization": f"Bearer {get_tdx_token()}"
}
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        # 找出包含該站名的路線
        matching = [
            r for r in data
            if any(
                station_name in s.get("StationName", {}).get("Zh_tw", "")
                for s in r.get("Stations", [])
            )
        ]
        if matching:
            route = matching[0]
            return {
                "路線名稱": route.get("RouteName", {}).get("Zh_tw", "未知"),
                "查詢站名": station_name,
                "說明": "請至台北捷運官網查看最新時刻表"
            }
    
    return {"錯誤": f"找不到 {station_name} 的捷運資訊"}


def get_parking(city: str = "taipei") -> dict:
    """
    呼叫台北市或新北市路邊停車即時資料
    city = "taipei"（台北市）或 "newtaipei"（新北市）
    """
    if city == "taipei":
        url = "https://tdx.transportdata.tw/api/basic/v1/Parking/OnStreet/ParkingSegmentAvailability/City/Taipei?%24top=30&%24format=JSON"
    else:
        url = "https://tdx.transportdata.tw/api/basic/v1/Parking/OnStreet/ParkingSegmentAvailability/City/NewTaipei?%24top=30&%24format=JSON"

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {get_tdx_token()}"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            items = data.get("CurbParkingSegmentAvailabilities", [])

            if items:
                results = []
                for item in items[:5]:
                    results.append({
                        "路段名稱": item.get("ParkingSegmentName", {}).get("Zh_tw", "未知"),
                        "總車位":   item.get("TotalSpaces", "?"),
                        "剩餘車位": item.get("AvailableSpaces", "?")
                    })
                return {"城市": "台北市" if city == "taipei" else "新北市", "停車資訊": results}
            else:
                return {"錯誤": "沒有停車資料"}
        else:
            return {"錯誤": f"API 錯誤，狀態碼：{response.status_code}"}

    except Exception as e:
        return {"錯誤": f"連線失敗：{str(e)}"}


# ════════════════════════════════════════════════════════════
#  定義給 Claude 看的「工具清單」
#  Claude 會根據使用者的問題，決定要呼叫哪些工具
# ════════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "get_google_route",          # 工具名稱（要和函式名一樣）
        "description": "查詢兩個地點之間的路線、距離和時間（使用 Google Maps）",
        "input_schema": {                    # 告訴 Claude 這個工具需要哪些輸入
            "type": "object",
            "properties": {
                "origin":      {"type": "string", "description": "出發地點"},
                "destination": {"type": "string", "description": "目的地點"}
            },
            "required": ["origin", "destination"]  # 這兩個欄位是必填的
        }
    },
    {
        "name": "get_taipei_bus",
        "description": "查詢台北市公車路線的即時到站時間",
        "input_schema": {
            "type": "object",
            "properties": {
                "route_name": {"type": "string", "description": "公車路線號碼，例如 '307'"}
            },
            "required": ["route_name"]
        }
    },
    {
        "name": "get_taipei_mrt",
        "description": "查詢台北捷運的站點和路線資訊",
        "input_schema": {
            "type": "object",
            "properties": {
                "station_name": {"type": "string", "description": "捷運站名，例如 '台北車站'"}
            },
            "required": ["station_name"]
        }
    },
    {
        "name": "get_parking",
        "description": "查詢台北市或新北市的路邊停車即時車位資訊",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "城市，填 'taipei' 或 'newtaipei'",
                    "enum": ["taipei", "newtaipei"]  # 只能填這兩個選項
                }
            },
            "required": ["city"]
        }
    }
]


# ════════════════════════════════════════════════════════════
#  核心函式：把使用者問題交給 Claude，讓它決定要呼叫哪些工具
# ════════════════════════════════════════════════════════════

def run_transport_agent(user_question: str) -> str:

    print(f"\n🚌 使用者問題：{user_question}")
    print("─" * 40)

    # 把四個工具函式放進清單
    tools_for_gemini = [
        get_google_route,
        get_taipei_bus,
        get_taipei_mrt,
        get_parking,
    ]

    system_prompt = (
        "你是一個台北交通助理，專門幫助使用者查詢台北的交通資訊。"
        "你可以查詢路線、台北公車、台北捷運、以及台北和新北的路邊停車格資訊。"
        "請用繁體中文回答，並盡量提供有用的交通建議。"
    )

    response = client.models.generate_content(
        #model="gemini-2.0-flash"
        model="gemini-3.1-flash-lite",
        # 新版用 gemini-2.0-flash，免費額度大
        contents=user_question,
        # 使用者的問題
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            # 系統提示放在 config 裡
            tools=tools_for_gemini,
            # 工具清單
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=False
                # False = 讓 Gemini 自動呼叫工具
            ),
        ),
    )

    print(f"✅ Gemini 回答完成")
    return response.text


# ════════════════════════════════════════════════════════════
#  程式進入點：直接執行這個檔案時會跑這裡
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # 測試幾個問題
    test_questions = [
        "從南港展覽館到台北101怎麼去？有幾種方式？",
        "台北101附近現在路邊停車哪裡有空位？",
        "262公車現在幾分鐘後到站？"
    ]
    
    for question in test_questions:
        answer = run_transport_agent(question)
        print(f"\n💬 回答：\n{answer}")
        print("═" * 50)