/** 錯誤與空狀態。錯誤用 role="alert"——讀螢幕的人不會自己去掃畫面找紅字。 */

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

export function EmptyHint(props: { text: string }) {
  return <p className="text-sm text-ink-soft">{props.text}</p>;
}
