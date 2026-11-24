// The grading page's view model: a quilt's grade, the tools to change it, section by section, and the commands that
// change it. Each change goes to the server at once, which draws it on the Looking Glass and keeps it; while one is on
// its way, only the newest waits, so the Looking Glass follows a slider as fast as it can. A save keeps the quilt with its
// grade as a new one, in the library. A copy replaces the grade with another quilt's, and can be undone until the next
// change.
import { useEffect, useRef, useState } from 'react';
import { selectGradeSources, selectShownId } from '../model/holoPiStore';
import { useHoloPiStore } from '../model/HoloPiStoreContext';
import type { Grade, GradeParameter, GradeState } from '../services/HoloPiApi';
import { useServices } from '../services/ServicesContext';
import { gradeState, groupBySection, isChanged } from '../utils/gradeUtils';
import { makeLatest } from '../utils/latestUtils';

/** A grade copied: from which quilt, and the grade to go back to, the one before the first copy. */
type Copy = { from: string; before: Grade };

export function useGrade(id: string) {
  const { state, dispatch } = useHoloPiStore();
  const { api } = useServices();
  const [parameters, setParameters] = useState<GradeParameter[] | null>(null);
  const [grade, setGrade] = useState<Grade | null>(null); // null until the server answers.
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedName, setSavedName] = useState<string | null>(null); // Of the last save, until the grade changes.
  const [copy, setCopy] = useState<Copy | null>(null); // The last copy, until the grade changes otherwise.
  const copyRef = useRef(0); // The number of the last copy or change: the answer to an older copy is stale.
  const [latest] = useState(() => makeLatest<{ grade: Grade; graded: GradeState | null }>(async next => {
    const result = await api.setGrade(id, next.grade);
    setError(result.ok ? null : result.error);
    if (result.ok) dispatch({ type: 'mediumGraded', id, grade: next.graded }); // The library says so too.
  }));

  // The tools and the grade, from the server, when the page opens. The library again too, for the quilts graded
  // elsewhere, whose grades can be copied: before any change here, which it would not have.
  useEffect(() => {
    const controller = new AbortController();
    async function read() {
      const [list, kept, media] = await Promise.all([api.listGradeParameters(controller.signal),
                                                     api.getGrade(id, controller.signal),
                                                     api.listMedia(controller.signal)]);
      if (controller.signal.aborted) return;
      if (media.ok) dispatch({ type: 'mediaListed', list: media.value });
      if (list.ok) setParameters(list.value);
      if (kept.ok) setGrade(kept.value);
      if (!list.ok) setError(list.error);
      else if (!kept.ok) setError(kept.error);
    }
    void read();
    return () => {
      controller.abort();
      copyRef.current++; // A copy still on its way would change the grade of a page that is gone.
    };
  }, [api, dispatch, id]);

  function apply(next: Grade, copied: Copy | null = null) {
    if (parameters === null) return;
    copyRef.current++;
    setCopy(copied);
    setGrade(next);
    setSavedName(null);
    latest.send({ grade: next, graded: gradeState(next, parameters) });
  }

  const ready = parameters !== null && grade !== null;
  const changed = ready && isChanged(grade, parameters);
  const showsOriginal = grade?.enabled === false;
  const canSave = changed && !showsOriginal && !saving;

  const sources = selectGradeSources(state, id);

  // Its values, as the server has them now, and on, even if the other quilt's are off: to copy them is to see them.
  async function copyFrom(from: string) {
    const source = sources.find(medium => medium.id === from);
    if (!ready || !source) return;
    const number = ++copyRef.current;
    const result = await api.getGrade(from);
    if (number !== copyRef.current) return;
    if (!result.ok) {
      setError(result.error);
    } else if (!isChanged(result.value, parameters)) {
      setError(`${source.name} is not graded any more`); // Reset elsewhere: it must not reset this one too.
    } else {
      apply({ enabled: true, values: result.value.values }, { from, before: copy?.before ?? grade });
    }
  }

  // The server saves the grade it has: the last change must have reached it.
  async function save() {
    if (!canSave) return;
    setSaving(true);
    setSavedName(null);
    await latest.settled();
    const result = await api.saveGraded(id);
    setSaving(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setError(null);
    setSavedName(result.value.name);
    dispatch({ type: 'mediumUploaded', medium: result.value });
  }

  const name = state.media?.find(medium => medium.id === id)?.name
    ?? (state.display?.media?.id === id ? state.display.media.name : id);

  return {
    name,
    sections: ready ? groupBySection(parameters, grade.values) : null,
    /** Whether the grade differs from the defaults, so that there is something to reset, or to compare with. */
    changed,
    /** Whether the Looking Glass shows the quilt without its grade, to compare. */
    showsOriginal,
    canSave,
    saving,
    /** The name of the new quilt, once saved, until the grade changes. */
    savedName,
    /** Whether the changes are seen: the Looking Glass may show something else meanwhile. */
    onScreen: selectShownId(state) === id,
    loading: !ready && error === null,
    error,
    /** Changes one value, and shows the grade again if the original was shown, so that the change is seen. */
    change(parameter: string, value: number) {
      if (grade) apply({ enabled: true, values: { ...grade.values, [parameter]: value } });
    },
    /** To compare: a copy can still be undone after it. */
    toggleOriginal() {
      if (grade) apply({ ...grade, enabled: !grade.enabled }, copy);
    },
    /** The quilts whose grade can be copied. */
    sources,
    /** The quilt whose grade was copied, until the grade changes otherwise. */
    copiedId: copy?.from ?? null,
    copyFrom,
    canUndoCopy: copy !== null,
    /** Puts back the grade from before the first copy. */
    undoCopy() {
      if (copy) apply(copy.before);
    },
    save,
    reset() {
      apply({ enabled: true, values: {} });
    },
  };
}
