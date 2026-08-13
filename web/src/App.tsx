/**
 * 路由與階段。
 *
 * ⚠️ 只有兩條路由：開場與舞台。手機外框**內部**的畫面切換是元件狀態，不進
 * 網址列——兩欄同時存在，讓它們去搶同一條網址只會互相覆蓋。
 *
 * ⚠️ **舞台掛在 `<Routes>` 外面**、由網址與動畫狀態決定顯不顯示。放進 `<Routes>`
 * 的話，`navigate("/stage")` 會把開場那一整棵子樹（含動畫期間先掛好的舞台）卸載、
 * 再掛一個全新的實例——`<Gate/>` 與 `<StagePage/>` 是不同元件型別、不同樹位置，
 * React 沒有第二種做法。「動畫期間就已經在載」於是完全不成立，而且是**靜默**
 * 失效：P1 的舞台不發請求所以看不出來，P2／P3 一接上資料載入就會白等一輪。
 *
 * ⚠️ **運營狀態的 hook 住在這裡而不是 GatePage 裡面**：BloomTransition 在 active
 * 翻轉時會把 children 從原位換到 overlay 底下的副本，那會卸載活著的 GatePage、
 * 掛上一個全新實例。狀態留在 GatePage 裡的話，動畫開始的那一瞬間畫面會閃回
 * 「正在確認服務狀態…」、按鈕變灰，並且對後端多打一次——而那正是整個展示的
 * 門面動畫，看的人會以為它壞了。
 */

import { useCallback, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router";

import { GatePage } from "./gate/GatePage";
import { useDemoStatus } from "./gate/useDemoStatus";
import { BloomTransition, type BloomOrigin } from "./stage/BloomTransition";
import { StagePage } from "./stage/StagePage";

const STAGE_PATH = "/stage";

function Demo() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  // 尾斜線容忍：貼網址給別人時多一個斜線很常見，而後端的單頁應用回退
  // （_SpaStaticFiles）對 /stage 與 /stage/ 兩者都成立——不容忍的話 /stage/
  // 會載入 SPA 但停在開場頁。
  const onStage = pathname.replace(/\/+$/, "") === STAGE_PATH;
  const [blooming, setBlooming] = useState(false);
  // 光暈的圓心由 GatePage 的按鈕交出來（見該檔 centerOf）。沒有值時
  // BloomTransition 會退回畫面正中央，不會壞。
  const [origin, setOrigin] = useState<BloomOrigin | undefined>(undefined);
  // 進了舞台仍持續輪詢：使用者按瀏覽器的上一頁回到開場時，看到的是新的狀態而不是
  // 十分鐘前那一份。成本是每十秒一次、伺服器端還有五秒快取擋著。
  const gate = useDemoStatus();
  const enterStage = useCallback(() => navigate(STAGE_PATH, { replace: true }), [navigate]);

  // ⚠️ 已經站在舞台上就代表轉場播完了，把旗標收回來。以前它住在 `<Routes>` 底下的
  // `Gate` 裡，換路由連元件一起卸載、旗標自然歸零；現在它活在路由之上，不收的話，
  // 任何從舞台回到開場的路徑（瀏覽器上一頁、P2／P3 可能加的「回到開場」按鈕）一到
  // 開場就會看到動畫重播，700 毫秒後又被彈回舞台——出不去。
  //
  // ⚠️ **在 render 期間收，不放 effect、也不併進 `enterStage`**：
  // ・併進 `enterStage`：`navigate` 是非同步的（router 會先跑完它自己那一段才通知
  //   訂閱者），`setBlooming(false)` 會單獨先繪製一次，那一格 `blooming` 與 `onStage`
  //   同時為 false——舞台被卸載重掛，正好把 I1 修掉的東西又弄回來（實測過）。
  // ・放 effect：effect 在 commit 之後才跑，會多一次繪製；而且 React 的 lint 規則
  //   直接擋（set-state-in-effect）。
  // render 期間調整狀態是 React 官方為此提供的做法：這一輪的輸出直接作廢、立刻用
  // 新值重繪，中間不會 commit 到 DOM，所以舞台一格都不會掉。
  if (blooming && onStage) {
    setBlooming(false);
  }

  return (
    <>
      {blooming || onStage ? <StagePage /> : null}
      {onStage ? null : (
        <BloomTransition active={blooming} onDone={enterStage} origin={origin}>
          <GatePage
            state={gate}
            onStart={(pressed) => {
              setOrigin(pressed);
              setBlooming(true);
            }}
          />
        </BloomTransition>
      )}
      {/* 畫面本身不由 <Routes> 決定（見上方說明），這裡只留「不認得的網址回開場」。 */}
      <Routes>
        <Route path="/" element={null} />
        <Route path={STAGE_PATH} element={null} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

export function App() {
  return (
    <BrowserRouter basename="/demo">
      <Demo />
    </BrowserRouter>
  );
}
