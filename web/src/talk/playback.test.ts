/** 網頁播放器：實作 talkSocket 的 PlayerLike 介面，並負責回收 blob URL。 */

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createWebPlayer,
  resetPendingReplyAudioForTest,
  revokeQueuedReplyAudio,
  revokeReplyAudio,
  UNLOCK_AUDIO_URI,
  writeReplyAudio,
} from "./playback";

afterEach(() => {
  vi.unstubAllGlobals();
  resetPendingReplyAudioForTest();
});

describe("writeReplyAudio", () => {
  it("把位元組換成可播放的 blob URL", () => {
    const createObjectURL = vi.fn().mockReturnValue("blob:fake-1");
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL: vi.fn() });
    expect(writeReplyAudio(new Uint8Array([1, 2, 3])).uri).toBe("blob:fake-1");
    expect(createObjectURL.mock.calls[0][0].type).toBe("audio/mp4");
  });

  it("空的位元組直接擲出，讓呼叫端丟掉這一則", () => {
    // 空音檔餵給播放器只會靜默失敗，而那一輪的字幕還是會顯示——長輩看得到字、
    // 等不到聲音，也不知道發生了什麼。
    expect(() => writeReplyAudio(new Uint8Array([]))).toThrow();
  });
});

describe("createWebPlayer", () => {
  it("replace 之後 play 會真的播", () => {
    const player = createWebPlayer();
    const element = (player as unknown as { element: HTMLAudioElement }).element;
    const play = vi.spyOn(element, "play").mockResolvedValue(undefined);
    player.replace({ uri: "blob:fake-1" });
    player.play();
    expect(element.src).toContain("blob:fake-1");
    expect(play).toHaveBeenCalled();
  });

  it("換下一則時回收上一則的 blob URL", () => {
    // 不回收的話，每一輪漏一個 blob，一場展示下來會累積幾十 MB 在記憶體裡。
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL: vi.fn(), revokeObjectURL });
    const player = createWebPlayer();
    player.replace({ uri: "blob:fake-1" });
    player.replace({ uri: "blob:fake-2" });
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:fake-1");
    expect(revokeObjectURL).not.toHaveBeenCalledWith("blob:fake-2");
  });

  it("不回收非 blob 的位址", () => {
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL: vi.fn(), revokeObjectURL });
    const player = createWebPlayer();
    player.replace({ uri: "https://cdn.example.com/a.m4a" });
    player.replace({ uri: "blob:fake-2" });
    expect(revokeObjectURL).not.toHaveBeenCalled();
  });

  it("播放結束時通知監聽者", () => {
    const player = createWebPlayer();
    const element = (player as unknown as { element: HTMLAudioElement }).element;
    const seen: boolean[] = [];
    player.addListener("playbackStatusUpdate", (status) => seen.push(status.didJustFinish));
    element.dispatchEvent(new Event("ended"));
    expect(seen).toEqual([true]);
  });

  it("移除監聽之後不再收到事件", () => {
    const player = createWebPlayer();
    const element = (player as unknown as { element: HTMLAudioElement }).element;
    const seen: boolean[] = [];
    const sub = player.addListener("playbackStatusUpdate", (s) => seen.push(s.didJustFinish));
    sub.remove();
    element.dispatchEvent(new Event("ended"));
    expect(seen).toEqual([]);
  });

  it("iOS 解鎖用的無聲檔播完不通知監聽者，換成真的回覆後才恢復正常通知", () => {
    // 這顆播放器是 unlockAudio 刻意共用的同一顆（iOS 的解鎖綁在單一
    // HTMLMediaElement 上）。若不濾掉，長輩第一次按下麥克風時，這段無聲檔
    // 播完的 ended 會被常駐監聽者誤判為「一則回覆播完了」，佇列是空的、
    // 提前把畫面切回待機——而長輩其實還在講話。
    const player = createWebPlayer();
    const element = (player as unknown as { element: HTMLAudioElement }).element;
    const seen: boolean[] = [];
    player.addListener("playbackStatusUpdate", (status) => seen.push(status.didJustFinish));

    player.replace({ uri: UNLOCK_AUDIO_URI });
    element.dispatchEvent(new Event("ended"));
    expect(seen).toEqual([]);

    player.replace({ uri: "blob:fake-1" });
    element.dispatchEvent(new Event("ended"));
    expect(seen).toEqual([true]);
  });

  it("dispose() 停止播放、回收目前的 blob URL 並釋放媒體資源，離開對講機畫面時徹底清乾淨", () => {
    // brief 的 Test 清單完全沒測到 dispose()——它是唯一負責「徹底清乾淨」的
    // 出口（例如長輩離開對講機畫面時呼叫），沒有測試會讓這條路徑的回收行為
    // 隨時被改壞而沒有任何訊號。
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL: vi.fn(), revokeObjectURL });
    const player = createWebPlayer();
    const element = (player as unknown as { element: HTMLAudioElement }).element;
    // jsdom 沒有實作 pause()／load()（呼叫真的實作會印一行 "Not implemented"
    // 噪音），故蓋掉實作，只驗證有沒有被呼叫到。
    const pause = vi.spyOn(element, "pause").mockImplementation(() => undefined);
    const load = vi.spyOn(element, "load").mockImplementation(() => undefined);
    player.replace({ uri: "blob:fake-1" });
    player.dispose();
    expect(pause).toHaveBeenCalled();
    expect(load).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:fake-1");
    expect(element.src).toBe("");
  });

  it("dispose() 連還沒排到 replace() 的 blob URL 也一併回收", () => {
    // 對應 Important 5：dispose() 是整個播放器要丟棄的時刻，此時不只回收
    // 「目前正在播的那一則」，佇列裡還沒輪到的那幾則也該一併清乾淨。
    const createObjectURL = vi
      .fn()
      .mockReturnValueOnce("blob:fake-1")
      .mockReturnValueOnce("blob:fake-2");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const player = createWebPlayer();
    const element = (player as unknown as { element: HTMLAudioElement }).element;
    vi.spyOn(element, "pause").mockImplementation(() => undefined);
    vi.spyOn(element, "load").mockImplementation(() => undefined);

    const playing = writeReplyAudio(new Uint8Array([1]));
    const queued = writeReplyAudio(new Uint8Array([2])); // 還沒排到 replace()
    player.replace(playing);

    player.dispose();

    expect(revokeObjectURL).toHaveBeenCalledWith(playing.uri);
    expect(revokeObjectURL).toHaveBeenCalledWith(queued.uri);
  });
});

describe("revokeQueuedReplyAudio", () => {
  it("回收所有還沒排到 replace() 的 blob URL，但不動傳入的 exceptUri", () => {
    // 對應 Important 5：長輩插嘴、播放佇列被 clear() 清空時，裡面還沒輪到
    // replace() 的那幾則本來一個都不會被回收——見本函式的模組註解。
    const createObjectURL = vi
      .fn()
      .mockReturnValueOnce("blob:fake-1")
      .mockReturnValueOnce("blob:fake-2")
      .mockReturnValueOnce("blob:fake-3");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });

    writeReplyAudio(new Uint8Array([1]));
    writeReplyAudio(new Uint8Array([2]));
    const playing = writeReplyAudio(new Uint8Array([3]));

    revokeQueuedReplyAudio(playing.uri);

    expect(revokeObjectURL).toHaveBeenCalledWith("blob:fake-1");
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:fake-2");
    expect(revokeObjectURL).not.toHaveBeenCalledWith("blob:fake-3");
  });

  it("已經透過 replace() 正常回收過的 uri 不會被重複回收", () => {
    const createObjectURL = vi
      .fn()
      .mockReturnValueOnce("blob:fake-1")
      .mockReturnValueOnce("blob:fake-2");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const player = createWebPlayer();

    const first = writeReplyAudio(new Uint8Array([1]));
    const second = writeReplyAudio(new Uint8Array([2]));
    player.replace(first);
    player.replace(second); // 正常換下一則時，first 已經被 revokeCurrent() 回收

    revokeObjectURL.mockClear();
    revokeQueuedReplyAudio();

    expect(revokeObjectURL).not.toHaveBeenCalledWith(first.uri);
    expect(revokeObjectURL).toHaveBeenCalledWith(second.uri);
  });
});

describe("revokeReplyAudio", () => {
  it("只回收指定的那一則，其餘還要補播的一則都不能動", () => {
    // ⚠️ 這正是它存在的理由（2026-08-01「改回補播」）：`revokeQueuedReplyAudio`
    // 是「除了這一則以外全部回收」，只留得住一個例外；而長輩插嘴之後等補播的
    // 不只是複數則，還是複數**輪**（`elder/useTalk.ts` 的 `deferredTurnsRef`，
    // 上限兩輪——同一天稍後續段直送引入之後，輪內常態就有 ack＋reply＋多個續段
    // 共四則以上，不再是原本「一輪最多兩則」的假設，這個理由因此比原本更強）。
    // 用那一支去擠掉最舊的一輪，會把還要補播的那幾輪、每輪好幾則一起毀掉——
    // 症狀是補播時播放器拿到失效的 blob URL、靜靜地沒有聲音。
    const createObjectURL = vi
      .fn()
      .mockReturnValueOnce("blob:fake-1")
      .mockReturnValueOnce("blob:fake-2");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });

    const dropped = writeReplyAudio(new Uint8Array([1]));
    const keep = writeReplyAudio(new Uint8Array([2]));

    revokeReplyAudio(dropped.uri);

    expect(revokeObjectURL).toHaveBeenCalledWith(dropped.uri);
    expect(revokeObjectURL).not.toHaveBeenCalledWith(keep.uri);
  });

  it("同一則回收兩次只會真的回收一次", () => {
    // 補播佇列擠掉一則、之後 cleanup 又全掃一次是正常路徑。重複呼叫
    // `URL.revokeObjectURL` 本身無害，但集合裡留著死掉的 uri 會讓「還沒回收的
    // 有哪些」這個問題答錯。
    const createObjectURL = vi.fn().mockReturnValueOnce("blob:fake-1");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });

    const dropped = writeReplyAudio(new Uint8Array([1]));
    revokeReplyAudio(dropped.uri);
    revokeObjectURL.mockClear();
    revokeReplyAudio(dropped.uri);

    expect(revokeObjectURL).not.toHaveBeenCalled();
  });

  it("分段續拉來的 https 簽章網址不在集合裡，不會被誤收", () => {
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL: vi.fn(), revokeObjectURL });

    revokeReplyAudio("https://cdn.example/c1.m4a");

    expect(revokeObjectURL).not.toHaveBeenCalled();
  });
});
