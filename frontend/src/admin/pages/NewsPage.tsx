import { useCallback, useState } from "react";

import { listNews } from "../api";
import { formatTime } from "../format";
import { strings } from "../strings";
import { useLoadable } from "../useLoadable";

const DAY_OPTIONS = [3, 7, 14];

/** 話題新聞檢視（D-74 消費端）：爬蟲近況——爬了什麼、來源、發布時間。 */
export function NewsPage() {
  const [days, setDays] = useState(DAY_OPTIONS[0]);
  // days 變動 → fetcher 參考更新 → useLoadable 自動重載。
  const { data, error, reload } = useLoadable(useCallback(() => listNews(days), [days]));

  if (error) return <p className="error-banner">{strings.common.loadFailedRefresh}</p>;
  if (!data) return <p>{strings.common.loading}</p>;
  return (
    <section>
      <h2>{strings.news.title}</h2>
      <p>
        <label>
          {strings.news.daysLabel}：
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {DAY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {strings.news.daysOption(option)}
              </option>
            ))}
          </select>
        </label>{" "}
        <button type="button" onClick={reload}>
          {strings.common.refresh}
        </button>
      </p>
      {data.length === 0 ? (
        <p>{strings.news.empty}</p>
      ) : (
        <table className="jobs-table">
          <thead>
            <tr>
              <th>{strings.news.columns.retrievedAt}</th>
              <th>{strings.news.columns.source}</th>
              <th>{strings.news.columns.publisher}</th>
              <th>{strings.news.columns.title}</th>
              <th>{strings.news.columns.publishedAt}</th>
            </tr>
          </thead>
          <tbody>
            {data.map((item) => (
              <tr key={item.news_item_id}>
                <td>{formatTime(item.retrieved_at)}</td>
                <td>
                  <code>{item.source_id}</code>
                </td>
                <td>{item.publisher}</td>
                <td>
                  <a href={item.url} target="_blank" rel="noreferrer">
                    {item.title}
                  </a>
                </td>
                <td>
                  {item.published_at
                    ? formatTime(item.published_at)
                    : strings.news.unknownPublishedAt}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p>
        <small>{strings.news.note}</small>
      </p>
    </section>
  );
}
