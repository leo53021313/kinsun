/** 共用 UI 小元件：兩種角色同一套；長輩端另以 size="big" 放大。
 *
 * 2026-08 改版：
 *   - 主要按鈕改暖黃底＋深靛藍字（不用白字，對比 9.4:1）
 *   - 全面改膠囊圓角；卡片加柔和陰影（家屬端原本無陰影）
 *   - 補上 focus 狀態（規格早已定，實作一直缺）
 *   - 新增 StatusPill：把「圖示＋底色＋文字」三重編碼收成一個元件
 */

import { type ReactNode, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
  type TextInputProps,
} from "react-native";

import { WarningCircleIcon } from "phosphor-react-native/src/icons/WarningCircle";

import { colors, elder, radius, spacing } from "@/lib/theme";

type ComponentSize = "normal" | "big";
type ButtonVariant = "primary" | "outline" | "subtle" | "danger";

export function Button(props: {
  label: string;
  onPress: () => void;
  size?: ComponentSize;
  disabled?: boolean;
  busy?: boolean;
  /** primary = 暖黃主鍵（每頁唯一）；outline = 靛藍外框；subtle = 淡底次要；danger = 破壞性 */
  variant?: ButtonVariant;
}) {
  const { label, onPress, size = "normal", disabled = false, busy = false } = props;
  const variant = props.variant ?? "primary";
  const isDisabled = disabled || busy;
  const busyColor = variant === "primary" ? colors.text : colors.primary;
  const [isFocused, setIsFocused] = useState(false);
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ busy, disabled: isDisabled }}
      disabled={isDisabled}
      onBlur={() => setIsFocused(false)}
      onFocus={() => setIsFocused(true)}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        size === "big" ? styles.buttonBig : null,
        variant === "outline" ? styles.buttonOutline : null,
        variant === "subtle" ? styles.buttonSubtle : null,
        variant === "danger" ? styles.buttonDanger : null,
        pressed ? pressedStyle(variant) : null,
        isFocused ? styles.focusRing : null,
        isDisabled ? styles.buttonDisabled : null,
      ]}
    >
      {busy ? (
        // busy 時仍顯示動作名稱（不換成「載入中」）
        <View style={styles.busyRow}>
          <ActivityIndicator color={busyColor} />
          <Text
            style={[
              styles.buttonLabel,
              labelStyle(variant),
              size === "big" ? styles.buttonLabelBig : null,
            ]}
          >
            {label}
          </Text>
        </View>
      ) : (
        <Text
          style={[
            styles.buttonLabel,
            labelStyle(variant),
            size === "big" ? styles.buttonLabelBig : null,
          ]}
        >
          {label}
        </Text>
      )}
    </Pressable>
  );
}

function pressedStyle(variant: ButtonVariant) {
  if (variant === "primary") return styles.buttonPressedPrimary;
  if (variant === "danger") return styles.buttonPressedDanger;
  return styles.buttonPressedSoft;
}

function labelStyle(variant: ButtonVariant) {
  if (variant === "outline") return styles.buttonLabelOutline;
  if (variant === "subtle") return styles.buttonLabelSubtle;
  if (variant === "danger") return styles.buttonLabelDanger;
  return styles.buttonLabelPrimary;
}

export function Field(props: TextInputProps & { label: string; hint?: string; size?: ComponentSize }) {
  const { label, hint, size = "normal", ...input } = props;
  return (
    <View style={styles.field}>
      <Text style={[styles.fieldLabel, size === "big" ? styles.fieldLabelBig : null]}>
        {label}
      </Text>
      <TextInput
        placeholderTextColor={colors.textSoft}
        {...input}
        accessibilityLabel={input.accessibilityLabel ?? label}
        style={[styles.input, size === "big" ? styles.inputBig : null, input.style]}
      />
      {hint ? (
        <Text style={[styles.fieldHint, size === "big" ? styles.fieldHintBig : null]}>
          {hint}
        </Text>
      ) : null}
    </View>
  );
}

/** 錯誤一律「顏色＋圖示＋文字」三重編碼（規則 6），拿掉顏色仍讀得懂。
 *
 * ⚠️ 圖示色用 `colors.danger`、文字色用 `colors.dangerText`：規則 15 明定前者只能
 * 用於邊界與圖示（對白底 3.7:1，非文字元件達標），文字要用深一階才過 4.5:1。
 *
 * ⚠️ 圖示掛 `accessibilityElementsHidden`：`accessibilityRole="alert"` 在外層那一格，
 * 讀螢幕的人聽到的是訊息本身，不該多聽一次「圖片」。 */
export function ErrorText(props: { message: string; size?: ComponentSize }) {
  if (!props.message) {
    return null;
  }
  const big = props.size === "big";
  return (
    // ⚠️ `accessible` 不可省：RN 的 View 預設不是無障礙元素，只掛
    // `accessibilityRole` 不會被讀螢幕軟體當成一則 alert（Text 預設才是）。
    <View accessible accessibilityRole="alert" style={styles.errorRow}>
      <View
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
        testID="error-icon"
      >
        <WarningCircleIcon color={colors.danger} size={big ? 26 : 20} weight="bold" />
      </View>
      <Text style={[styles.error, big ? styles.errorBig : null]}>{props.message}</Text>
    </View>
  );
}

export function Section(props: {
  title?: string;
  children: ReactNode;
  inset?: boolean;
  size?: ComponentSize;
}) {
  return (
    <View style={[styles.section, props.inset ? styles.sectionInset : null]}>
      {props.title ? (
        <Text style={[styles.sectionTitle, props.size === "big" ? styles.sectionTitleBig : null]}>
          {props.title}
        </Text>
      ) : null}
      {props.children}
    </View>
  );
}

export function EmptyHint(props: { text: string; size?: ComponentSize }) {
  return (
    <Text style={[styles.empty, props.size === "big" ? styles.emptyBig : null]}>
      {props.text}
    </Text>
  );
}

/** 狀態一律「顏色＋圖示＋文字」三重編碼，拿掉顏色仍讀得懂。
 *  icon 傳 Phosphor 元件，由呼叫端決定；這裡只管配色與版面。 */
export function StatusPill(props: {
  tone: "done" | "pending" | "overdue" | "critical" | "info";
  label: string;
  icon: ReactNode;
  size?: ComponentSize;
}) {
  const { tone, label, icon, size = "normal" } = props;
  const tint = PILL_TONES[tone];
  return (
    <View style={[styles.pill, { backgroundColor: tint.bg }]}>
      {icon}
      <Text
        style={[
          styles.pillLabel,
          { color: tint.fg },
          size === "big" ? styles.pillLabelBig : null,
        ]}
      >
        {label}
      </Text>
    </View>
  );
}

const PILL_TONES = {
  done: { bg: "#EAF7F3", fg: colors.successText },
  pending: { bg: "#FDF6DE", fg: colors.warningText },
  overdue: { bg: "#FDF6DE", fg: colors.warningText },
  critical: { bg: "#FDF0F0", fg: colors.dangerText },
  info: { bg: colors.background, fg: colors.primary },
} as const;

/** 可複選的時段／類型選項。強制 48dp 觸控下限。 */
export function Chip(props: {
  label: string;
  selected: boolean;
  onPress: () => void;
  role?: "radio" | "checkbox";
  size?: ComponentSize;
}) {
  const { label, selected, onPress, role = "checkbox", size = "normal" } = props;
  const [isFocused, setIsFocused] = useState(false);
  return (
    <Pressable
      accessibilityRole={role}
      // ⚠️ 依 role 分流：checkbox 的勾選狀態是 `checked`，`selected` 是
      // radio／tab／option 那一類用的。送錯的話讀螢幕軟體不會播報勾選與否
      // ——看得見的人有底色可看，聽的人什麼都沒有。（原本兩種 role 都送
      // `selected`，那是從交付稿 handoff/ui.tsx:182 繼承下來的。）
      accessibilityState={role === "checkbox" ? { checked: selected } : { selected }}
      onBlur={() => setIsFocused(false)}
      onFocus={() => setIsFocused(true)}
      onPress={onPress}
      style={() => [
        styles.chip,
        selected ? styles.chipSelected : null,
        isFocused ? styles.focusRing : null,
      ]}
    >
      <Text
        style={[
          styles.chipLabel,
          selected ? styles.chipLabelSelected : null,
          size === "big" ? styles.chipLabelBig : null,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    backgroundColor: colors.action,
    borderRadius: radius.pill,
    paddingVertical: 14,
    paddingHorizontal: spacing.l,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 56, // 家屬端主要按鈕；48 仍是所有可點區域的下限
    // 主鍵陰影（elevation.action）
    shadowColor: "#D6A820",
    shadowOpacity: 0.28,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 8 },
    elevation: 4,
  },
  buttonBig: { minHeight: 84, paddingVertical: 0 },
  buttonOutline: {
    backgroundColor: colors.surface,
    borderWidth: 2,
    borderColor: colors.primary,
    shadowOpacity: 0,
    elevation: 0,
  },
  buttonSubtle: {
    backgroundColor: colors.background,
    shadowOpacity: 0,
    elevation: 0,
  },
  buttonDanger: {
    backgroundColor: colors.surface,
    borderWidth: 2,
    borderColor: colors.danger,
    shadowOpacity: 0,
    elevation: 0,
  },
  // 按下＝換色＋縮放，不只換色
  buttonPressedPrimary: {
    backgroundColor: colors.actionPressed,
    transform: [{ scale: 0.98 }],
  },
  buttonPressedSoft: { backgroundColor: colors.border, transform: [{ scale: 0.98 }] },
  buttonPressedDanger: { backgroundColor: "#FDF0F0", transform: [{ scale: 0.98 }] },
  buttonDisabled: { opacity: 0.5 },
  busyRow: { flexDirection: "row", alignItems: "center", gap: spacing.s },
  buttonLabel: { fontSize: 18, fontWeight: "700" },
  buttonLabelPrimary: { color: colors.text },
  buttonLabelBig: { fontSize: elder.fontBig },
  buttonLabelOutline: { color: colors.primary },
  buttonLabelSubtle: { color: colors.primary },
  buttonLabelDanger: { color: colors.dangerText },
  // focus：2px 靛藍描邊＋2px 外偏移
  focusRing: {
    borderWidth: 2,
    borderColor: colors.primary,
    outlineWidth: 2,
    outlineColor: colors.primary,
    outlineOffset: 2,
  },
  field: { gap: spacing.xs },
  fieldLabel: { fontSize: 16, fontWeight: "600", color: colors.text },
  fieldLabelBig: { fontSize: elder.fontMin },
  fieldHint: { fontSize: 15, color: colors.textSoft },
  fieldHintBig: { fontSize: elder.fontMin },
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.control,
    paddingHorizontal: spacing.m,
    minHeight: 60,
    fontSize: 18,
    color: colors.text,
  },
  inputBig: { fontSize: elder.fontMin },
  errorRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs + 2 },
  error: { flexShrink: 1, color: colors.dangerText, fontSize: 16 },
  errorBig: { fontSize: elder.fontMin },
  section: {
    backgroundColor: colors.surface,
    borderRadius: radius.card,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.l,
    gap: spacing.s,
    // elevation.card
    shadowColor: "#2F3273",
    shadowOpacity: 0.05,
    shadowRadius: 24,
    shadowOffset: { width: 0, height: 8 },
    elevation: 2,
  },
  // 內嵌區塊刻意比外層卡片「凹」一階
  sectionInset: {
    backgroundColor: colors.background,
    borderWidth: 0,
    borderRadius: radius.control,
    shadowOpacity: 0,
    elevation: 0,
  },
  sectionTitle: { fontSize: 20, fontWeight: "700", color: colors.text },
  sectionTitleBig: { fontSize: elder.fontMin },
  empty: { fontSize: 16, color: colors.textSoft },
  emptyBig: { fontSize: elder.fontMin },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs + 2,
    alignSelf: "flex-start",
    borderRadius: radius.pill,
    paddingHorizontal: 14,
    paddingVertical: 6,
  },
  pillLabel: { fontSize: 15, fontWeight: "700" },
  pillLabelBig: { fontSize: elder.fontMin },
  chip: {
    minHeight: 48, // 硬下限
    justifyContent: "center",
    paddingHorizontal: 18,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  chipSelected: { backgroundColor: colors.primaryPressed, borderColor: colors.primaryPressed },
  chipLabel: { fontSize: 17, fontWeight: "600", color: colors.text },
  chipLabelSelected: { color: "#FFFFFF", fontWeight: "700" },
  chipLabelBig: { fontSize: elder.fontMin },
});
