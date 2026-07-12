import { useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { Button, EmptyHint, ErrorText, Field, Section } from "@/components/ui";
import {
  ApiError,
  createMedication,
  deleteMedication,
  listMedications,
  updateMedication,
  type Medication,
} from "@/lib/api";
import { SLOTS, slotLabel } from "@/lib/medicationSlots";
import { useSession } from "@/lib/SessionProvider";
import { colors, spacing } from "@/lib/theme";

/** 用藥管理：清單＋編輯／刪除＋同頁表單（App 版編輯，取代走 LINE 端）。 */
export default function MedicationsManage() {
  const { elderId } = useLocalSearchParams<{ elderId: string }>();
  const { session } = useSession();
  const token = session?.token ?? "";
  const [medications, setMedications] = useState<Medication[] | null>(null);
  const [name, setName] = useState("");
  const [slots, setSlots] = useState<string[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    if (!elderId || !token) {
      return;
    }
    try {
      setMedications(await listMedications(elderId, token));
    } catch {
      setError("載入失敗，請稍後再試。");
    }
  }, [elderId, token]);

  useEffect(() => {
    reload();
  }, [reload]);

  function toggleSlot(value: string) {
    setSlots((cur) => (cur.includes(value) ? cur.filter((s) => s !== value) : [...cur, value]));
  }

  function resetForm() {
    setName("");
    setSlots([]);
    setEditingId(null);
  }

  async function submit() {
    const trimmed = name.trim();
    if (!elderId || !trimmed || slots.length === 0) {
      return;
    }
    setError("");
    setBusy(true);
    try {
      if (editingId) {
        await updateMedication(elderId, editingId, trimmed, slots, token);
      } else {
        await createMedication(elderId, trimmed, slots, token);
      }
      resetForm();
      await reload();
    } catch (exc) {
      setError(exc instanceof ApiError ? exc.message : "儲存失敗，請稍後再試。");
    } finally {
      setBusy(false);
    }
  }

  function startEdit(med: Medication) {
    setEditingId(med.medication_id);
    setName(med.name);
    setSlots([...med.slots]);
    setError("");
  }

  function confirmRemove(med: Medication) {
    Alert.alert("刪除用藥", `確定要刪除「${med.name}」嗎？`, [
      { text: "取消", style: "cancel" },
      {
        text: "刪除",
        style: "destructive",
        onPress: async () => {
          if (!elderId) {
            return;
          }
          try {
            await deleteMedication(elderId, med.medication_id, token);
            if (editingId === med.medication_id) {
              resetForm();
            }
            await reload();
          } catch (exc) {
            setError(exc instanceof ApiError ? exc.message : "刪除失敗，請稍後再試。");
          }
        },
      },
    ]);
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <ErrorText message={error} />

      <Section title="固定用藥">
        {medications === null ? (
          <EmptyHint text="載入中…" />
        ) : medications.length === 0 ? (
          <EmptyHint text="還沒有用藥，從下方新增第一筆。" />
        ) : (
          medications.map((m) => (
            <View key={m.medication_id} style={styles.item}>
              <Text style={styles.itemText} maxFontSizeMultiplier={1.6}>
                {m.name}（{m.slots.map(slotLabel).join("、")}）
              </Text>
              <View style={styles.itemActions}>
                <Button label="編輯" variant="outline" onPress={() => startEdit(m)} />
                <Button label="刪除" variant="outline" onPress={() => confirmRemove(m)} />
              </View>
            </View>
          ))
        )}
      </Section>

      <Section title={editingId ? "編輯用藥" : "新增用藥"}>
        <Field label="藥名" value={name} onChangeText={setName} placeholder="例：降血壓藥" />
        <Text style={styles.slotTitle} maxFontSizeMultiplier={1.6}>
          提醒時段（可複選）
        </Text>
        <View style={styles.slotRow}>
          {SLOTS.map((s) => {
            const selected = slots.includes(s.value);
            return (
              <Pressable
                key={s.value}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: selected }}
                onPress={() => toggleSlot(s.value)}
                style={[styles.chip, selected ? styles.chipSelected : null]}
              >
                <Text
                  maxFontSizeMultiplier={1.6}
                  style={[styles.chipText, selected ? styles.chipTextSelected : null]}
                >
                  {s.label}
                </Text>
              </Pressable>
            );
          })}
        </View>
        <Button
          label={editingId ? "更新" : "新增"}
          onPress={submit}
          busy={busy}
          disabled={!name.trim() || slots.length === 0}
        />
        {editingId ? <Button label="取消編輯" variant="outline" onPress={resetForm} /> : null}
      </Section>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.m, gap: spacing.m },
  item: { gap: spacing.xs },
  itemText: { fontSize: 17, color: colors.text },
  itemActions: { flexDirection: "row", gap: spacing.s },
  slotTitle: { fontSize: 16, fontWeight: "600", color: colors.textSoft },
  slotRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.s },
  chip: {
    borderWidth: 2,
    borderColor: colors.border,
    backgroundColor: colors.surface,
    borderRadius: 999,
    paddingVertical: 10,
    paddingHorizontal: spacing.m,
  },
  chipSelected: { borderColor: colors.primary, backgroundColor: colors.primary },
  chipText: { fontSize: 16, fontWeight: "600", color: colors.text },
  chipTextSelected: { color: "#FFFFFF" },
});
