/** 錯誤、中性提示與空狀態。錯誤用 role="alert"——讀螢幕的人不會自己去掃畫面找紅字。 */

export function ErrorText(props: { message: string }) {
  if (!props.message) {
    return null;
  }
  return (
    <p role="alert" className="text-sm text-danger">
      {props.message}
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
