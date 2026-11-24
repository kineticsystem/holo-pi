// The grading page's view model: a quilt's grade, the tools to change it, section by section, and the commands that
// change it. Each change goes to the server at once, which draws it on the Looking Glass and keeps it; while one is on
// its way, only the newest waits, so the Looking Glass follows a slider as fast as it can. A save keeps the quilt with its
// grade as a new one, in the library.
import { useEffect, useState } from 'react';
import { selectShownId } from '../model/holoPiStore';
import { useHoloPiStore } from '../model/HoloPiStoreContext';
import type { Grade, GradeParameter, GradeState } from '../services/HoloPiApi';
import { useServices } from '../services/ServicesContext';
import { gradeState, groupBySection, isChanged } from '../utils/gradeUtils';
import { makeLatest } from '../utils/latestUtils';

export function useGrade(id: string) {
  const { state, dispatch } = useHoloPiStore();
  const { api } = useServices();
  const [parameters, setParameters] = useState<GradeParameter[] | null>(null);
  const [grade, setGrade] = useState<Grade | null>(null); // null until the server answers.
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedName, setSavedName] = useState<string | null>(null); // Of the last save, until the grade changes.
  const [latest] = useState(() => makeLatest<{ grade: Grade; graded: GradeState | null }>(async next => {
    const result = await api.setGrade(id, next.grade);
    setError(result.ok ? null : result.error);
    if (result.ok) dispatch({ type: 'mediumGraded', id, grade: next.graded }); // The library says so too.
  }));

  // The tools and the grade, from the server, when the page opens.
  useEffect(() => {
    const controller = new AbortController();
    async function read() {
      const [list, kept] = await Promise.all([api.listGradeParameters(controller.signal),
                                              api.getGrade(id, controller.signal)]);
      if (controller.signal.aborted) return;
      if (list.ok) setParameters(list.value);
      if (kept.ok) setGrade(kept.value);
      if (!list.ok) setError(list.error);
      else if (!kept.ok) setError(kept.error);
    }
    void read();
    return () => controller.abort();
  }, [api, id]);

  function apply(next: Grade) {
    if (parameters === null) return;
    setGrade(next);
    setSavedName(null);
    latest.send({ grade: next, graded: gradeState(next, parameters) });
  }

  const ready = parameters !== null && grade !== null;
  const changed = ready && isChanged(grade, parameters);
  const showsOriginal = grade?.enabled === false;
  const canSave = changed && !showsOriginal && !saving;

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
    toggleOriginal() {
      if (grade) apply({ ...grade, enabled: !grade.enabled });
    },
    save,
    reset() {
      apply({ enabled: true, values: {} });
    },
  };
}
