/** 網頁播放器：實作 talkSocket 的 PlayerLike 介面，並負責回收 blob URL。 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { createWebPlayer, writeReplyAudio } from "./playback";

afterEach(() => vi.unstubAllGlobals());

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

  it("dispose() 停止播放並回收目前的 blob URL，離開對講機畫面時徹底清乾淨", () => {
    // brief 的 Test 清單完全沒測到 dispose()——它是唯一負責「徹底清乾淨」的
    // 出口（例如長輩離開對講機畫面時呼叫），沒有測試會讓這條路徑的回收行為
    // 隨時被改壞而沒有任何訊號。
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL: vi.fn(), revokeObjectURL });
    const player = createWebPlayer();
    const element = (player as unknown as { element: HTMLAudioElement }).element;
    // jsdom 沒有實作 pause()（呼叫真的實作會印一行 "Not implemented" 噪音），
    // 故蓋掉實作，只驗證有沒有被呼叫到。
    const pause = vi.spyOn(element, "pause").mockImplementation(() => undefined);
    player.replace({ uri: "blob:fake-1" });
    player.dispose();
    expect(pause).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:fake-1");
    expect(element.src).toBe("");
  });
});
