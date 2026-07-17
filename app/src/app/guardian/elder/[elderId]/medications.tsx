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
import { useSession, useSignOutOnAuthError } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, spacing } from "@/lib/theme";

/** 用藥管理：清單＋編輯／刪除＋同頁表單（App 版編輯，取代走 LINE 端）。 */
export default function MedicationsManage() {
  const { elderId } = useLocalSearchParams<{ elderId: string }>();
  const { session } = useSession();
  const signOutOn401 = useSignOutOnAuthError();
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
    } catch (exc) {
      if (await signOutOn401(exc)) return;
      setError(strings.common.loadFailed);
    }
  }, [elderId, token, signOutOn401]);

  useEffect(() => {
    // reload 是 async，它的每一個 setState 都在 await 之後——effect 的同步執行
    // 期間一個都不會跑，故不會有規則擔心的連鎖重繪。規則無法跨函式邊界分析
    // reload 內部，只看到「effect 呼叫了會 setState 的函式」就保守回報。
    // 已驗證 void reload() 也壓不掉，非寫法問題。
    // eslint-disable-next-line react-compiler/set-state-in-effect
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
      if (await signOutOn401(exc)) return;
      setError(exc instanceof ApiError ? exc.message : strings.common.saveFailed);
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
    Alert.alert(strings.medications.deleteTitle, strings.medications.confirmDelete(med.name), [
      { text: strings.common.cancel, style: "cancel" },
      {
        text: strings.common.delete,
        style: "destructive",
        onPress: async () => {
          if (!elderId) {
            return;
          }
          setBusy(true);
          try {
            await deleteMedication(elderId, med.medication_id, token);
            if (editingId === med.medication_id) {
              resetForm();
            }
            await reload();
          } catch (exc) {
            if (await signOutOn401(exc)) return;
            setError(exc instanceof ApiError ? exc.message : strings.common.deleteFailed);
          } finally {
            setBusy(false);
          }
        },
      },
    ]);
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <ErrorText message={error} />

      <Section title={strings.medications.listSection}>
        {medications === null ? (
          <EmptyHint text={strings.common.loading} />
        ) : medications.length === 0 ? (
          <EmptyHint text={strings.medications.empty} />
        ) : (
          medications.map((m) => (
            <View key={m.medication_id} style={styles.item}>
              <Text style={styles.itemText} maxFontSizeMultiplier={1.6}>
                {m.name}（{m.slots.map(slotLabel).join("、")}）
              </Text>
              <View style={styles.itemActions}>
                <Button label={strings.common.edit} variant="outline" disabled={busy} onPress={() => startEdit(m)} />
                <Button label={strings.common.delete} variant="outline" disabled={busy} onPress={() => confirmRemove(m)} />
              </View>
            </View>
          ))
        )}
      </Section>

      <Section title={editingId ? strings.medications.editSection : strings.medications.addSection}>
        <Field label={strings.medications.nameLabel} value={name} onChangeText={setName} placeholder={strings.medications.namePlaceholder} />
        <Text style={styles.slotTitle} maxFontSizeMultiplier={1.6}>
          {strings.medications.slotsLabel}
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
          label={editingId ? strings.common.update : strings.common.create}
          onPress={submit}
          busy={busy}
          disabled={!name.trim() || slots.length === 0}
        />
        {editingId ? <Button label={strings.common.cancelEdit} variant="outline" onPress={resetForm} /> : null}
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
