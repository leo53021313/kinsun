/** 改回診時間（批次 6）：只送現有 ScheduleInput 真正支援的日期與時間。 */

import { useLocalSearchParams, useRouter } from "expo-router";
import { useEffect, useState } from "react";
import { Alert, ScrollView, StyleSheet, Text, View } from "react-native";

import { Button, EmptyHint, ErrorText, Field, Section } from "@/components/ui";
import {
  ApiError,
  deleteSchedule,
  listSchedules,
  updateSchedule,
  type ScheduleGroup,
} from "@/lib/api";
import { toOccurrences } from "@/lib/schedules";
import { useSession, useSignOutOnAuthError } from "@/lib/SessionProvider";
import { strings } from "@/lib/strings";
import { colors, spacing } from "@/lib/theme";

type BusyAction = "save" | "delete" | null;

export default function EditAppointmentScreen() {
  const router = useRouter();
  const { scheduleId, elderId } = useLocalSearchParams<{
    scheduleId: string;
    elderId: string;
  }>();
  const { session } = useSession();
  const signOutOn401 = useSignOutOnAuthError();
  const [schedule, setSchedule] = useState<ScheduleGroup | null>(null);
  const [when, setWhen] = useState("");
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [busyAction, setBusyAction] = useState<BusyAction>(null);

  useEffect(() => {
    if (!session || !elderId || !scheduleId) return;
    let alive = true;
    (async () => {
      try {
        const groups = await listSchedules(elderId, session.token, "appointment");
        const found = groups.find((group) => group.group_id === scheduleId) ?? null;
        if (alive) {
          setSchedule(found);
          setWhen(found ? formatAppointmentWhen(found.event_at) : "");
          if (!found) setError(strings.editAppointment.notFound);
        }
      } catch (exc) {
        if (await signOutOn401(exc)) return;
        if (alive) setError(strings.common.loadFailed);
      } finally {
        if (alive) setLoaded(true);
      }
    })();
    return () => {
      alive = false;
    };
  }, [elderId, scheduleId, session, signOutOn401]);

  async function save() {
    if (!session || !elderId || !schedule) return;
    const built = toOccurrences("appointment", { slots: [], when });
    if (!built) {
      setError(strings.editAppointment.invalidWhen);
      return;
    }
    setError("");
    setBusyAction("save");
    try {
      await updateSchedule(
        elderId,
        schedule.group_id,
        { kind: "appointment", title: schedule.title, ...built },
        session.token,
      );
      router.back();
    } catch (exc) {
      if (await signOutOn401(exc)) return;
      setError(exc instanceof ApiError ? exc.message : strings.common.saveFailed);
    } finally {
      setBusyAction(null);
    }
  }

  async function remove() {
    if (!session || !elderId || !schedule) return;
    setError("");
    setBusyAction("delete");
    try {
      await deleteSchedule(elderId, schedule.group_id, session.token);
      router.back();
    } catch (exc) {
      if (await signOutOn401(exc)) return;
      setError(exc instanceof ApiError ? exc.message : strings.common.deleteFailed);
    } finally {
      setBusyAction(null);
    }
  }

  function confirmRemove() {
    if (!schedule) return;
    Alert.alert(
      strings.editAppointment.deleteTitle,
      strings.editAppointment.deleteConfirm(schedule.title),
      [
        { text: strings.common.cancel, style: "cancel" },
        { text: strings.common.delete, style: "destructive", onPress: remove },
      ],
    );
  }

  if (!loaded) {
    return (
      <View style={styles.stateScreen}>
        <EmptyHint text={strings.common.loading} />
      </View>
    );
  }

  if (!schedule) {
    return (
      <View style={styles.stateScreen}>
        <ErrorText message={error || strings.editAppointment.notFound} />
      </View>
    );
  }

  const isBusy = busyAction !== null;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Section title={schedule.title}>
        <Field
          label={strings.editAppointment.whenLabel}
          value={when}
          onChangeText={setWhen}
          placeholder={strings.schedules.whenPlaceholder("appointment")}
          hint={strings.editAppointment.whenHint}
        />
      </Section>

      <Text style={styles.note} maxFontSizeMultiplier={2}>
        {strings.editAppointment.savedEffect}
      </Text>

      <ErrorText message={error} />
      <Button
        label={strings.editAppointment.save}
        onPress={save}
        busy={busyAction === "save"}
        disabled={isBusy}
      />
      <Button
        label={strings.editAppointment.deleteThis}
        variant="danger"
        onPress={confirmRemove}
        busy={busyAction === "delete"}
        disabled={isBusy}
      />
    </ScrollView>
  );
}

export function formatAppointmentWhen(eventAt: number | null): string {
  if (eventAt === null) return "";
  const value = new Date(eventAt * 1000);
  const date = `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
  if (value.getHours() === 0 && value.getMinutes() === 0) return date;
  return `${date} ${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  stateScreen: { flex: 1, backgroundColor: colors.background, padding: spacing.m },
  content: { padding: spacing.m, gap: spacing.l },
  note: { fontSize: 16, lineHeight: 25, color: colors.textSoft },
});
