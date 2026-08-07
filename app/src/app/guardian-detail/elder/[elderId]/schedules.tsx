import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useCallback, useState } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { Button, EmptyHint, ErrorText, Field, Section } from "@/components/ui";
import {
  ApiError,
  createSchedule,
  deleteSchedule,
  listSchedules,
  updateSchedule,
  type ScheduleGroup,
  type ScheduleInput,
} from "@/lib/api";
import { KIND_OPTIONS, SLOTS, describeGroup, toOccurrences } from "@/lib/schedules";
import { useSession, useSignOutOnAuthError } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, spacing } from "@/lib/theme";

/**
 * 行程管理（D-76 P3）：用藥、回診與長輩自訂提醒共用一頁，取代原本的兩個畫面。
 *
 * 三種類型問的問題不同，故「時間」欄位隨類型換輸入方式：用藥選時段（或直接打時刻）、
 * 回診填日期、其他填重複方式。組成 API 請求的邏輯全在 lib/schedules.ts，這裡只管畫面。
 */
export default function SchedulesManage() {
  const { elderId } = useLocalSearchParams<{ elderId: string }>();
  const router = useRouter();
  const { session } = useSession();
  const signOutOn401 = useSignOutOnAuthError();
  const token = session?.token ?? "";
  const [groups, setGroups] = useState<ScheduleGroup[] | null>(null);
  const [kind, setKind] = useState<ScheduleGroup["kind"]>("medication");
  const [title, setTitle] = useState("");
  const [slots, setSlots] = useState<string[]>([]);
  const [when, setWhen] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    if (!elderId || !token) {
      return;
    }
    try {
      setGroups(await listSchedules(elderId, token));
    } catch (exc) {
      if (await signOutOn401(exc)) return;
      setError(strings.common.loadFailed);
    }
  }, [elderId, token, signOutOn401]);

  // 獨立的回診編輯頁儲存／刪除後會 back 到這裡；每次重新取得焦點都要重載清單。
  useFocusEffect(
    useCallback(() => {
      void reload();
    }, [reload]),
  );

  function toggleSlot(value: string) {
    setSlots((cur) => (cur.includes(value) ? cur.filter((s) => s !== value) : [...cur, value]));
  }

  function resetForm() {
    setTitle("");
    setSlots([]);
    setWhen("");
    setEditingId(null);
  }

  function buildBody(): ScheduleInput | null {
    const trimmed = title.trim();
    if (!trimmed) {
      return null;
    }
    const built = toOccurrences(kind, { slots, when });
    if (!built) {
      return null;
    }
    return { kind, title: trimmed, ...built };
  }

  async function submit() {
    const body = buildBody();
    if (!elderId || !body) {
      setError(strings.schedules.whenRequired);
      return;
    }
    setError("");
    setBusy(true);
    try {
      if (editingId) {
        await updateSchedule(elderId, editingId, body, token);
      } else {
        await createSchedule(elderId, body, token);
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

  function startEdit(group: ScheduleGroup) {
    setEditingId(group.group_id);
    setKind(group.kind);
    setTitle(group.title);
    setSlots([]);
    setWhen("");
    setError(strings.schedules.editHint);
  }

  function editGroup(group: ScheduleGroup) {
    if (group.kind !== "appointment" || !elderId) {
      startEdit(group);
      return;
    }
    router.push({
      pathname: "/guardian-detail/schedule/[scheduleId]/edit",
      params: { scheduleId: group.group_id, elderId },
    });
  }

  function confirmRemove(group: ScheduleGroup) {
    Alert.alert(strings.schedules.deleteTitle, strings.schedules.confirmDelete(group.title), [
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
            await deleteSchedule(elderId, group.group_id, token);
            if (editingId === group.group_id) {
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

      <Section title={strings.schedules.listSection}>
        {groups === null ? (
          <EmptyHint text={strings.common.loading} />
        ) : groups.length === 0 ? (
          <EmptyHint text={strings.schedules.empty} />
        ) : (
          groups.map((g) => (
            <View key={g.group_id} style={styles.item}>
              <Text style={styles.itemText} maxFontSizeMultiplier={1.6}>
                {describeGroup(g)}
              </Text>
              {/* 長輩自己用說的建的提醒也在這一頁，標出來家屬才知道那不是自己設的。 */}
              {g.created_by === "elder" ? (
                <Text style={styles.byElder} maxFontSizeMultiplier={1.6}>
                  {strings.schedules.byElder}
                </Text>
              ) : null}
              <View style={styles.itemActions}>
                <Button
                  label={strings.common.edit}
                  variant="outline"
                  disabled={busy}
                  onPress={() => editGroup(g)}
                />
                <Button
                  label={strings.common.delete}
                  variant="outline"
                  disabled={busy}
                  onPress={() => confirmRemove(g)}
                />
              </View>
            </View>
          ))
        )}
      </Section>

      <Section title={editingId ? strings.schedules.editSection : strings.schedules.addSection}>
        <Text style={styles.fieldTitle} maxFontSizeMultiplier={1.6}>
          {strings.schedules.kindLabel}
        </Text>
        <View style={styles.chipRow}>
          {KIND_OPTIONS.map((option) => {
            const selected = kind === option.value;
            return (
              <Pressable
                key={option.value}
                accessibilityRole="radio"
                accessibilityState={{ selected }}
                onPress={() => setKind(option.value)}
                style={[styles.chip, selected ? styles.chipSelected : null]}
              >
                <Text
                  maxFontSizeMultiplier={1.6}
                  style={[styles.chipText, selected ? styles.chipTextSelected : null]}
                >
                  {option.label}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <Field
          label={strings.schedules.titleLabel}
          value={title}
          onChangeText={setTitle}
          placeholder={strings.schedules.titlePlaceholder(kind)}
        />

        {kind === "medication" ? (
          <>
            <Text style={styles.fieldTitle} maxFontSizeMultiplier={1.6}>
              {strings.schedules.slotsLabel}
            </Text>
            <View style={styles.chipRow}>
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
            <Field
              label={strings.schedules.customTimeLabel}
              value={when}
              onChangeText={setWhen}
              placeholder="07:30"
            />
          </>
        ) : (
          <Field
            label={strings.schedules.whenLabel(kind)}
            value={when}
            onChangeText={setWhen}
            placeholder={strings.schedules.whenPlaceholder(kind)}
          />
        )}

        <Button
          label={editingId ? strings.common.update : strings.common.create}
          onPress={submit}
          busy={busy}
          disabled={!title.trim()}
        />
        {editingId ? (
          <Button label={strings.common.cancelEdit} variant="outline" onPress={resetForm} />
        ) : null}
      </Section>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.background },
  content: { padding: spacing.m, gap: spacing.m },
  item: { gap: spacing.xs },
  itemText: { fontSize: 17, color: colors.text },
  byElder: { fontSize: 14, color: colors.textSoft },
  itemActions: { flexDirection: "row", gap: spacing.s },
  fieldTitle: { fontSize: 16, fontWeight: "600", color: colors.textSoft },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.s },
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
