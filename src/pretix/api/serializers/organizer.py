from pretix.api.serializers.i18n import I18nAwareModelSerializer
from pretix.api.serializers.order import CompatibleJSONField
from pretix.base.models import Organizer, SeatingPlan
from pretix.base.models.seating import SeatingPlanLayoutValidator


class OrganizerSerializer(I18nAwareModelSerializer):
    class Meta:
        model = Organizer
        fields = ('name', 'slug')


class SeatingPlanSerializer(I18nAwareModelSerializer):
    layout = CompatibleJSONField(
        validators=[SeatingPlanLayoutValidator()]
    )

    class Meta:
        model = SeatingPlan
        fields = ('id', 'name', 'layout')
