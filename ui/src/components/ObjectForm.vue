<script setup lang="ts">
// The form of an object or an item of ours, the first group box of the Objects tab, always there (ComposeBar, as everywhere: the legend reads "Add an object", or "Edit NAME" for the object being changed). With an object selected in the list it changes that object
// and the main button reads Save; with none selected it adds a new one and the button reads Add; Cancel (and Esc, also with the cursor in a field) leaves the selection and clears the form completely (no place, the default symbol, nothing else); Add stays off, saying so in its title, until there is a place. The fields: the name (that of an object that is being changed stays; a new one is always an object, an item of ours that is being changed stays an item), the symbol (the picture and its name, a click opens the picker, as in the My station tab), the position (the row Location of the My station tab, components/LocationField.vue: **Choose on map**, a click on the map, or the
// coordinates or a locator typed behind the place), the comment (the characters it has left are the counter beside the buttons), the course and speed (behind a closed fold, Moving, which is open for an object that has either; Up and Down step either by one, with Shift by ten), and behind a second closed fold, Advanced, as in the My station tab: the path the object goes by (the placeholder is the beacon's), its category (a choice of the standard groups of local info by their plain names, or Other... with a code of our own; the value is the code that goes on the air, and a station that asks for the group is sent the object) and, once there is a category, whether it is sent only when asked; Advanced
// is open for an object being changed that has a path, a group or the tick. Every field of ours has its (i) after it, as the settings have (InfoTip); the symbol and the place are the controls of the My station tab, which have none. A field with something wrong is red and says what under it. Save is on when there is a name, a place and a symbol and nothing is wrong; the daemon checks it all again.
import { useReceiveOnly } from "@/composables/useReceiveOnly";
import { rxOnlyReason } from "@/lib/compose";
import { computed, ref, useId, watch } from "vue";
import ComposeBar from "@/components/ComposeBar.vue";
import DisclosureBox from "@/components/DisclosureBox.vue";
import InfoTip from "@/components/InfoTip.vue";
import LocationField from "@/components/LocationField.vue";
import SymbolField from "@/components/SymbolField.vue";
import { t } from "@/i18n";
import type { MessageId } from "@/i18n/catalogue";
import type { OwnObjectsView } from "@/composables/useOwnObjects";
import { leftTitle } from "@/lib/compose";
import { placeOfText } from "@/lib/locator";
import { CATEGORY_CODES, categoryMessage, isStandardCategory } from "@/lib/qrucategories";
import { commentLimit, draftProblems, draftReady, NAME_MAX, steppedCourse, steppedSpeed } from "@/lib/ownobjects";
import { LIMITS } from "@/protocol/lists";

const props = defineProps<{ form: OwnObjectsView; fallbackPath: string }>();
const id = useId();
const qruMax = LIMITS.object.qruGroupMax;
const draft = props.form.draft; // (the form's own state, kept as one object for as long as the page lives)
const problems = computed(() => draftProblems(draft));
const rxOnly = useReceiveOnly();
const ready = computed(() => draftReady(draft));
/** The place the draft has in words (the text beside the button); null while it is no place. */
const place = computed(() => placeOfText(draft.lat, draft.lon));
/** The fold Moving (course and speed) is open while the draft has either: an object being changed that moves, or a value typed. */
const moving = computed(() => draft.course.trim() !== "" || draft.speed.trim() !== "");
/** The fold Advanced (path, category, sent only when asked) is open while the draft has any of them. */
const advanced = computed(() => draft.path.trim() !== "" || draft.qru.trim() !== "" || draft.onRequest);
/** The choice of the Category that stands for "Other...": a word of our own, which has its field. */
const OTHER = "other";
const own = ref(false); // ("Other..." chosen and no word typed yet)
const choice = computed(() => (isStandardCategory(draft.qru) ? draft.qru.trim().toUpperCase() : draft.qru.trim() !== "" || own.value ? OTHER : ""));
watch(
  () => [props.form.editing, props.form.dirty],
  () => {
    if (props.form.editing !== null || !props.form.dirty) own.value = false;
  },
);

/** A choice of the Category: the standard code, none (which also drops "Send only when asked", as it is out of sight), or a word of our own to type. */
function choose(value: string): void {
  own.value = value === OTHER;
  draft.qru = value === OTHER ? (isStandardCategory(draft.qru) ? "" : draft.qru) : value;
  if (value === "") draft.onRequest = false;
}
/** The name of an (i) for a screen reader: "About Path". */
const about = (field: MessageId) => t("settings.about", { label: t(field) });
const left = computed(() => commentLimit(draft) - draft.comment.trim().length);
</script>

<template>
  <ComposeBar
    class="objform"
    :label="form.editing === null ? t('objects.form.new') : t('objects.edit_label', { name: form.editing })"
    :left="left"
    :left-title="leftTitle(left, 'comment')"
    @submit="form.save()"
  >
    <div class="field" :class="{ invalid: problems.name }" :title="problems.name">
      <label :for="`${id}-name`">{{ t("objects.field.name") }}</label>
      <div class="field-control">
        <input
          :id="`${id}-name`"
          v-model="draft.name"
          class="input mono"
          type="text"
          :maxlength="NAME_MAX"
          :readonly="form.editing !== null"
          autocomplete="off"
          spellcheck="false"
        />
        <InfoTip :label="about('objects.field.name')"
          ><span class="info-line">{{ t("objects.tip.name", { max: NAME_MAX }) }}</span></InfoTip
        >
      </div>
    </div>
    <SymbolField :id="`${id}-symbol`" v-model:symbol="draft.symbol" />
    <LocationField
      :id="`${id}-place`"
      :place="place"
      :picking="form.placing"
      :lat="draft.lat"
      :lon="draft.lon"
      :errors="{ lat: problems.lat, lon: problems.lon }"
      @pick="form.togglePlacing()"
      @update:lat="draft.lat = $event"
      @update:lon="draft.lon = $event"
    />
    <div class="field" :class="{ invalid: problems.comment }" :title="problems.comment">
      <label :for="`${id}-comment`">{{ t("objects.field.comment") }}</label>
      <div class="field-control">
        <input :id="`${id}-comment`" v-model="draft.comment" class="input" type="text" autocomplete="off" />
        <InfoTip :label="about('objects.field.comment')"
          ><span class="info-line">{{ t("objects.tip.comment") }}</span></InfoTip
        >
      </div>
    </div>
    <DisclosureBox :key="`${form.editing ?? ''}-moving`" class="settings-fold" :title="t('objects.field.moving')" :open="moving">
      <div class="field" :class="{ invalid: problems.course }" :title="problems.course">
        <label :for="`${id}-course`">{{ t("objects.field.course") }}</label>
        <div class="field-control">
          <input
            :id="`${id}-course`"
            v-model="draft.course"
            class="input mono"
            type="text"
            inputmode="numeric"
            autocomplete="off"
            @keydown.up.prevent="draft.course = steppedCourse(draft.course, $event.shiftKey ? 10 : 1)"
            @keydown.down.prevent="draft.course = steppedCourse(draft.course, $event.shiftKey ? -10 : -1)"
          />
          <span class="unit muted">{{ t("objects.unit.deg") }}</span>
          <InfoTip :label="about('objects.field.course')"
            ><span class="info-line">{{ t("objects.tip.course") }}</span></InfoTip
          >
        </div>
      </div>
      <div class="field" :class="{ invalid: problems.speed }" :title="problems.speed">
        <label :for="`${id}-speed`">{{ t("objects.field.speed") }}</label>
        <div class="field-control">
          <input
            :id="`${id}-speed`"
            v-model="draft.speed"
            class="input mono"
            type="text"
            inputmode="decimal"
            autocomplete="off"
            @keydown.up.prevent="draft.speed = steppedSpeed(draft.speed, $event.shiftKey ? 10 : 1)"
            @keydown.down.prevent="draft.speed = steppedSpeed(draft.speed, $event.shiftKey ? -10 : -1)"
          />
          <span class="unit muted">km/h</span>
          <InfoTip :label="about('objects.field.speed')"
            ><span class="info-line">{{ t("objects.tip.speed") }}</span></InfoTip
          >
        </div>
      </div>
    </DisclosureBox>
    <DisclosureBox :key="`${form.editing ?? ''}-advanced`" class="settings-fold" :title="t('settings.fold.advanced')" :open="advanced">
      <div class="field" :class="{ invalid: problems.path }" :title="problems.path">
        <label :for="`${id}-path`">{{ t("objects.field.path") }}</label>
        <div class="field-control">
          <input
            :id="`${id}-path`"
            v-model="draft.path"
            class="input mono"
            type="text"
            :placeholder="fallbackPath || t('route.default')"
            autocomplete="off"
            spellcheck="false"
          />
          <InfoTip :label="about('objects.field.path')"
            ><span class="info-line">{{ t("objects.tip.path") }}</span></InfoTip
          >
        </div>
      </div>
      <div class="field">
        <label :for="`${id}-category`">{{ t("objects.field.category") }}</label>
        <div class="field-control">
          <select :id="`${id}-category`" class="input" :value="choice" @change="choose(($event.target as HTMLSelectElement).value)">
            <option value="">{{ t("objects.category.none") }}</option>
            <option v-for="code in CATEGORY_CODES" :key="code" :value="code">{{ t(categoryMessage(code)) }}</option>
            <option :value="OTHER">{{ t("objects.category.other") }}</option>
          </select>
          <InfoTip :label="about('objects.field.category')">
            <span class="info-line">{{ t("objects.tip.category") }}</span>
          </InfoTip>
        </div>
      </div>
      <div v-if="choice === OTHER" class="field" :class="{ invalid: problems.qru }" :title="problems.qru">
        <label :for="`${id}-qru`">{{ t("objects.field.category_code") }}</label>
        <div class="field-control">
          <input
            :id="`${id}-qru`"
            v-model="draft.qru"
            class="input mono"
            type="text"
            :maxlength="qruMax"
            autocomplete="off"
            spellcheck="false"
            @input="draft.qru = draft.qru.toUpperCase()"
          />
          <InfoTip :label="about('objects.field.category_code')">
            <span class="info-line">{{ t("objects.tip.category_code", { max: qruMax }) }}</span>
          </InfoTip>
        </div>
      </div>
      <div v-if="choice !== '' || draft.onRequest" class="field">
        <label :for="`${id}-asked`">{{ t("objects.field.on_request") }}</label>
        <div class="field-control">
          <input :id="`${id}-asked`" v-model="draft.onRequest" class="check" type="checkbox" />
          <InfoTip :label="about('objects.field.on_request')" picture="request"
            ><span class="info-line">{{ t("objects.tip.on_request") }}</span></InfoTip
          >
        </div>
      </div>
    </DisclosureBox>
    <template #buttons>
      <button type="button" class="btn" :disabled="!form.dirty && !form.placing" @click="form.cancel()">{{ t("objects.form.cancel") }}</button>
      <button
        type="submit"
        class="btn primary"
        :disabled="!ready || rxOnly"
        :title="rxOnly ? rxOnlyReason() : place === null ? t('objects.form.need_place') : undefined"
      >
        {{ form.editing === null ? t("objects.form.add") : t("objects.form.save") }}
      </button>
    </template>
  </ComposeBar>
</template>
