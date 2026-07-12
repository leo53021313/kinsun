import DateTimePicker from "@react-native-community/datetimepicker";
import { useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Alert, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { Button, EmptyHint, ErrorText, Field, Section } from "@/components/ui";
import {
  ApiError,
  createAppointment,
  deleteAppointment,
  listAppointments,
  updateAppointment,
  type Appointment,
} from "@/lib/api";
import { useSession, useSignOutOnAuthError } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, spacing } from "@/lib/theme";

/** 以本地時區組 YYYY-MM-DD（不用 toISOString，避免 UTC 位移跨日）。 */
function toDateString(d: Date): string {
  const month = `${d.getMonth() + 1}`.padStart(2, "0");
  const day = `${d.getDate()}`.padStart(2, "0");
  return `${d.getFullYear()}-${month}-${day}`;
}

function toTimeString(d: Date): string {
  const hours = `${d.getHours()}`.padStart(2, "0");
  const minutes = `${d.getMinutes()}`.padStart(2, "0");
  return `${hours}:${minutes}`;
}

/** 回診管理：清單＋編輯／刪除＋同頁表單；日期用系統選擇器、最早選今天。 */
export default function AppointmentsManage() {
  const { elderId } = useLocalSearchParams<{ elderId: string }>();
  const { session } = useSession();
  const signOutOn401 = useSignOutOnAuthError();
  const token = session?.token ?? "";
  const [appointments, setAppointments] = useState<Appointment[] | null>(null);
  const [date, setDate] = useState("");
  const [time, setTime] = useState("");
  const [label, setLabel] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [showPicker, setShowPicker] = useState(false);
  const [showTimePicker, setShowTimePicker] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    if (!elderId || !token) {
      return;
    }
    try {
      setAppointments(await listAppointments(elderId, token));
    } catch (exc) {
      if (await signOutOn401(exc)) return;
      setError(strings.common.loadFailed);
    }
  }, [elderId, token, signOutOn401]);

  useEffect(() => {
    reload();
  }, [reload]);

  function resetForm() {
    setDate("");
    setTime("");
    setLabel("");
    setEditingId(null);
    setShowPicker(false);
    setShowTimePicker(false);
  }

  async function submit() {
    const trimmed = label.trim();
    if (!elderId || !date || !trimmed) {
      return;
    }
    setError("");
    setBusy(true);
    try {
      if (editingId) {
        await updateAppointment(elderId, editingId, date, trimmed, time, token);
      } else {
        await createAppointment(elderId, date, trimmed, time, token);
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

  function startEdit(appt: Appointment) {
    setEditingId(appt.appointment_id);
    setDate(appt.date);
    setTime(appt.time);
    setLabel(appt.label);
    setError("");
  }

  function confirmRemove(appt: Appointment) {
    const shown = appt.time ? `${appt.date} ${appt.time}` : appt.date;
    Alert.alert(strings.appointments.deleteTitle, strings.appointments.confirmDelete(shown, appt.label), [
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
            await deleteAppointment(elderId, appt.appointment_id, token);
            if (editingId === appt.appointment_id) {
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

      <Section title={strings.appointments.listSection}>
        {appointments === null ? (
          <EmptyHint text={strings.common.loading} />
        ) : appointments.length === 0 ? (
          <EmptyHint text={strings.appointments.empty} />
        ) : (
          appointments.map((a) => (
            <View key={a.appointment_id} style={styles.item}>
              <Text style={styles.itemText} maxFontSizeMultiplier={1.6}>
                {a.date}
                {a.time ? ` ${a.time}` : ""}｜{a.label}
              </Text>
              <View style={styles.itemActions}>
                <Button label={strings.common.edit} variant="outline" disabled={busy} onPress={() => startEdit(a)} />
                <Button label={strings.common.delete} variant="outline" disabled={busy} onPress={() => confirmRemove(a)} />
              </View>
            </View>
          ))
        )}
      </Section>

      <Section title={editingId ? strings.appointments.editSection : strings.appointments.addSection}>
        <View style={styles.dateField}>
          <Text style={styles.dateLabel} maxFontSizeMultiplier={1.6}>
            {strings.appointments.dateLabel}
          </Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => setShowPicker((cur) => !cur)}
            style={styles.dateInput}
          >
            <Text
              maxFontSizeMultiplier={1.6}
              style={[styles.dateText, date ? null : styles.datePlaceholder]}
            >
              {date || strings.appointments.datePlaceholder}
            </Text>
          </Pressable>
        </View>
        {showPicker ? (
          <DateTimePicker
            value={date ? new Date(`${date}T00:00:00`) : new Date()}
            mode="date"
            display={Platform.OS === "ios" ? "inline" : "default"}
            minimumDate={new Date()}
            onChange={(event, selected) => {
              setShowPicker(false);
              if (event.type === "set" && selected) {
                setDate(toDateString(selected));
              }
            }}
          />
        ) : null}
        <View style={styles.dateField}>
          <Text style={styles.dateLabel} maxFontSizeMultiplier={1.6}>
            {strings.appointments.timeLabel}
          </Text>
          <Pressable
            accessibilityRole="button"
            onPress={() => setShowTimePicker((cur) => !cur)}
            style={styles.dateInput}
          >
            <Text
              maxFontSizeMultiplier={1.6}
              style={[styles.dateText, time ? null : styles.datePlaceholder]}
            >
              {time || strings.appointments.timePlaceholder}
            </Text>
          </Pressable>
        </View>
        {showTimePicker ? (
          <DateTimePicker
            value={time ? new Date(`2000-01-01T${time}:00`) : new Date()}
            mode="time"
            display={Platform.OS === "ios" ? "spinner" : "default"}
            onChange={(event, selected) => {
              setShowTimePicker(false);
              if (event.type === "set" && selected) {
                setTime(toTimeString(selected));
              }
            }}
          />
        ) : null}
        <Field
          label={strings.appointments.contentLabel}
          value={label}
          onChangeText={setLabel}
          placeholder={strings.appointments.contentPlaceholder}
        />
        <Button
          label={editingId ? strings.common.update : strings.common.create}
          onPress={submit}
          busy={busy}
          disabled={!date || !label.trim()}
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
  dateField: { gap: spacing.xs },
  dateLabel: { fontSize: 16, fontWeight: "600", color: colors.textSoft },
  dateInput: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: spacing.m,
    paddingVertical: 12,
  },
  dateText: { fontSize: 18, color: colors.text },
  datePlaceholder: { color: colors.textSoft },
});
