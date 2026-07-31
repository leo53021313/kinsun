/** 錯誤、中性提示與空狀態。錯誤用 role="alert"——讀螢幕的人不會自己去掃畫面找紅字。 */

export function ErrorText(props: { message: string; size?: "normal" | "big" }) {
  const { message, size = "normal" } = props;
  if (!message) {
    return null;
  }
  // ⚠️ 長輩端審查發現：本元件固定 `text-sm`（14px），低於長輩端 `--text-elder-min`
  // （22px）下限——五種綁定錯誤＋六種相機錯誤那十一句「告訴他下一步做什麼」的
  // 話，全部曾經以全畫面最小字級呈現。加 `size` prop 而非全域放大：家屬端（沿用
  // 預設 `"normal"`）不該被連帶放大。
  return (
    <p role="alert" className={size === "big" ? "text-elder-min text-danger" : "text-sm text-danger"}>
      {message}
    </p>
  );
}

/**
 * 中性提示：成功回饋與操作指示（「已設定完成。」「修改後請重新填一次提醒時間。」）。
 *
 * ⚠️ 這種訊息**不可以**借用 `ErrorText`：紅字＋`role="alert"` 會被螢幕報讀軟體當成
 * 警示、打斷目前的朗讀，而使用者剛剛做的是一個成功的操作。`role="status"` 是禮貌
 * 宣告（等目前朗讀結束才播報），語意才對得上；顏色也不用 danger。
 *
 * 與 `EmptyHint` 分開：後者是「這裡沒有東西」的說明文字，不必被播報。
 */
export function NoticeText(props: { message: string }) {
  if (!props.message) {
    return null;
  }
  return (
    <p role="status" className="text-sm text-ink-soft">
      {props.message}
    </p>
  );
}

export function EmptyHint(props: { text: string }) {
  return <p className="text-sm text-ink-soft">{props.text}</p>;
}
