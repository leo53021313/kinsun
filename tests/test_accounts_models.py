from kinsun.accounts.models import (
    Channel,
    ChannelBinding,
    ConsentBy,
    Elder,
    ElderGuardian,
    Invite,
    InviteRole,
    PrincipalType,
    Role,
)


def test_enums():
    assert Role.PRIMARY.value == "primary"
    assert InviteRole.ELDER.value == "elder"
    assert ConsentBy.SELF.value == "self"


def test_elder_default_line_none():
    assert Elder("e1", "阿公").line_user_id is None


def test_invite_defaults():
    inv = Invite("c1", "e1", InviteRole.GUARDIAN, 100.0, max_attempts=5)
    assert inv.attempts == 0
    assert inv.used_at is None
    assert ElderGuardian("e1", "g1", Role.PRIMARY, 1, True).can_view_transcript is True


def test_channel_binding_model():
    binding = ChannelBinding(
        channel=Channel.LINE,
        external_id="U123",
        principal_type=PrincipalType.ELDER,
        principal_id="e1",
        created_at=1000.0,
    )
    assert binding.channel == Channel.LINE
    assert binding.channel.value == "line"
    assert Channel.APP.value == "app"
    assert binding.principal_type == PrincipalType.ELDER
    assert PrincipalType.GUARDIAN.value == "guardian"
    assert binding.principal_id == "e1"
    assert binding.created_at == 1000.0
