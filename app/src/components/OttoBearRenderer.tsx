import { Asset } from "expo-asset";
import { Image } from "expo-image";
import { File } from "expo-file-system";
import { Platform, StyleSheet, View } from "react-native";
import { useEffect, useRef, useState } from "react";
import { WebView } from "react-native-webview";

import {
  createOttoSyncCommand,
  parseOttoRendererEvent,
  type OttoSpeechCue,
} from "@/lib/ottoBridge";
import type { TalkVisualState } from "@/lib/talkPresentation";

const RENDERER_BASE_URL = "https://kinsun-renderer.invalid/";
let rendererHtmlPromise: Promise<string> | null = null;

function loadRendererHtml(): Promise<string> {
  if (rendererHtmlPromise) return rendererHtmlPromise;
  rendererHtmlPromise = (async () => {
    const asset = Asset.fromModule(require("@/assets/otto/renderer.html"));
    await asset.downloadAsync();
    if (Platform.OS === "web") {
      const response = await fetch(asset.uri);
      if (!response.ok) throw new Error(`renderer asset HTTP ${response.status}`);
      return response.text();
    }
    if (!asset.localUri) throw new Error("renderer asset 沒有 localUri");
    return new File(asset.localUri).text();
  })().catch((error) => {
    // 載入失敗後允許下次重新嘗試；畫面仍保留靜態 fallback，不阻擋長輩說話。
    rendererHtmlPromise = null;
    throw error;
  });
  return rendererHtmlPromise;
}

export function OttoBearRenderer(props: {
  state: TalkVisualState;
  speechCue: OttoSpeechCue | null;
}) {
  const [html, setHtml] = useState<string | null>(null);
  const [isReady, setIsReady] = useState(false);
  const webViewRef = useRef<WebView>(null);
  const isReadyRef = useRef(false);
  const sequenceRef = useRef(0);
  const latestCommandRef = useRef(
    createOttoSyncCommand(0, props.state, props.speechCue),
  );

  useEffect(() => {
    // react-native-webview 不支援瀏覽器；Expo Web 保留靜態暫用圖，不載入無法使用的
    // renderer，也不讓套件自己的紅字 fallback 出現在長輩畫面。
    if (Platform.OS === "web") return;
    let alive = true;
    void loadRendererHtml()
      .then((value) => {
        if (alive) setHtml(value);
      })
      .catch(() => {
        if (alive) setHtml(null);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    sequenceRef.current += 1;
    const command = createOttoSyncCommand(
      sequenceRef.current,
      props.state,
      props.speechCue,
    );
    latestCommandRef.current = command;
    if (isReadyRef.current) webViewRef.current?.postMessage(JSON.stringify(command));
  }, [props.speechCue, props.state]);

  return (
    <View style={styles.container}>
      {!isReady || Platform.OS === "web" ? (
        <Image
          source={require("@/assets/images/akin-hero.png")}
          contentFit="contain"
          transition={160}
          style={styles.fallback}
        />
      ) : null}
      {html && Platform.OS !== "web" ? (
        <WebView
          ref={webViewRef}
          source={{ html, baseUrl: RENDERER_BASE_URL }}
          originWhitelist={["*"]}
          onShouldStartLoadWithRequest={(request) =>
            request.url === "about:blank" || request.url.startsWith(RENDERER_BASE_URL)
          }
          onMessage={(event) => {
            const message = parseOttoRendererEvent(event.nativeEvent.data);
            if (message?.type !== "ready") return;
            isReadyRef.current = true;
            setIsReady(true);
            webViewRef.current?.postMessage(JSON.stringify(latestCommandRef.current));
          }}
          onError={() => {
            isReadyRef.current = false;
            setIsReady(false);
          }}
          javaScriptEnabled
          domStorageEnabled={false}
          allowFileAccess={false}
          allowUniversalAccessFromFileURLs={false}
          setSupportMultipleWindows={false}
          mixedContentMode="never"
          cacheEnabled={false}
          incognito
          scrollEnabled={false}
          bounces={false}
          overScrollMode="never"
          showsHorizontalScrollIndicator={false}
          showsVerticalScrollIndicator={false}
          accessible={false}
          accessibilityElementsHidden
          importantForAccessibility="no-hide-descendants"
          pointerEvents="none"
          style={[styles.webView, !isReady ? styles.webViewHidden : null]}
          testID="otto-bear-renderer"
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { width: "100%", height: "100%" },
  fallback: { position: "absolute", inset: 0 },
  webView: { flex: 1, backgroundColor: "transparent" },
  webViewHidden: { opacity: 0 },
});
