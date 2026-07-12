/** 共用 UI 小元件：兩種角色同一套；長輩端另以 size="big" 放大。 */

import { type ReactNode } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
  type TextInputProps,
} from "react-native";

import { colors, elder, spacing } from "@/lib/theme";

export function Button(props: {
  label: string;
  onPress: () => void;
  size?: "normal" | "big";
  disabled?: boolean;
  busy?: boolean;
  variant?: "primary" | "outline";
}) {
  const { label, onPress, size = "normal", disabled = false, busy = false } = props;
  const variant = props.variant ?? "primary";
  return (
    <Pressable
      accessibilityRole="button"
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        size === "big" ? styles.buttonBig : null,
        variant === "outline" ? styles.buttonOutline : null,
        pressed ? styles.buttonPressed : null,
        disabled || busy ? styles.buttonDisabled : null,
      ]}
    >
      {busy ? (
        <ActivityIndicator color={variant === "outline" ? colors.primary : "#FFFFFF"} />
      ) : (
        <Text
          maxFontSizeMultiplier={1.6}
          style={[
            styles.buttonLabel,
            size === "big" ? styles.buttonLabelBig : null,
            variant === "outline" ? styles.buttonLabelOutline : null,
          ]}
        >
          {label}
        </Text>
      )}
    </Pressable>
  );
}

export function Field(props: TextInputProps & { label: string }) {
  const { label, ...input } = props;
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel} maxFontSizeMultiplier={1.6}>
        {label}
      </Text>
      <TextInput
        placeholderTextColor={colors.textSoft}
        {...input}
        style={[styles.input, input.style]}
      />
    </View>
  );
}

export function ErrorText(props: { message: string }) {
  if (!props.message) {
    return null;
  }
  return (
    <Text style={styles.error} maxFontSizeMultiplier={2}>
      {props.message}
    </Text>
  );
}

export function Section(props: { title: string; children: ReactNode }) {
  return (
    <View style={styles.section}>
      <Text style={styles.sectionTitle} maxFontSizeMultiplier={1.6}>
        {props.title}
      </Text>
      {props.children}
    </View>
  );
}

export function EmptyHint(props: { text: string }) {
  return (
    <Text style={styles.empty} maxFontSizeMultiplier={2}>
      {props.text}
    </Text>
  );
}

const styles = StyleSheet.create({
  button: {
    backgroundColor: colors.primary,
    borderRadius: 14,
    paddingVertical: 14,
    paddingHorizontal: spacing.l,
    alignItems: "center",
    justifyContent: "center",
  },
  buttonBig: { paddingVertical: 24, borderRadius: 22 },
  buttonOutline: {
    backgroundColor: colors.surface,
    borderWidth: 2,
    borderColor: colors.primary,
  },
  buttonPressed: { backgroundColor: colors.primaryPressed },
  buttonDisabled: { opacity: 0.5 },
  buttonLabel: { color: "#FFFFFF", fontSize: 18, fontWeight: "700" },
  buttonLabelBig: { fontSize: elder.fontBig },
  buttonLabelOutline: { color: colors.primary },
  field: { gap: spacing.xs },
  fieldLabel: { fontSize: 16, fontWeight: "600", color: colors.textSoft },
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: spacing.m,
    paddingVertical: 12,
    fontSize: 18,
    color: colors.text,
  },
  error: { color: colors.danger, fontSize: 16 },
  section: {
    backgroundColor: colors.surface,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.m,
    gap: spacing.s,
  },
  sectionTitle: { fontSize: 18, fontWeight: "700", color: colors.text },
  empty: { fontSize: 16, color: colors.textSoft },
});
