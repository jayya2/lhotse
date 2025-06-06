"""
Since the tests in this module handle very different types of *Set classes,
we try to leverage 'duration' attribute which is shared by all tested types of items
(cuts, features, recordings, supervisions).
"""
import random
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from lhotse import CutSet, FeatureSet, RecordingSet, SupervisionSet, combine
from lhotse.cut.text import TextExample
from lhotse.lazy import LazyJsonlIterator, LazyRepeater, LazyTxtIterator
from lhotse.testing.dummies import DummyManifest, as_lazy
from lhotse.testing.fixtures import with_dill_enabled
from lhotse.utils import fastcopy, is_module_available


@pytest.mark.parametrize(
    "manifest_type", [RecordingSet, SupervisionSet, FeatureSet, CutSet]
)
def test_combine_lazy(manifest_type):
    expected = DummyManifest(manifest_type, begin_id=0, end_id=200)
    with as_lazy(DummyManifest(manifest_type, begin_id=0, end_id=68)) as part1, as_lazy(
        DummyManifest(manifest_type, begin_id=68, end_id=136)
    ) as part2, as_lazy(
        DummyManifest(manifest_type, begin_id=136, end_id=200)
    ) as part3:
        combined = combine(part1, part2, part3)
        # Equivalent under iteration
        assert list(combined) == list(expected)


@pytest.mark.parametrize(
    "manifest_type", [RecordingSet, SupervisionSet, FeatureSet, CutSet]
)
def test_subset_first_lazy(manifest_type):
    any_set = DummyManifest(manifest_type, begin_id=0, end_id=200)
    expected = DummyManifest(manifest_type, begin_id=0, end_id=10)
    subset = any_set.subset(first=10)
    assert subset == expected


@pytest.mark.parametrize(
    "manifest_type", [RecordingSet, SupervisionSet, FeatureSet, CutSet]
)
def test_subset_last_lazy(manifest_type):
    any_set = DummyManifest(manifest_type, begin_id=0, end_id=200)
    expected = DummyManifest(manifest_type, begin_id=190, end_id=200)
    subset = any_set.subset(last=10)
    assert subset == expected


@pytest.mark.parametrize(
    "manifest_type", [RecordingSet, SupervisionSet, FeatureSet, CutSet]
)
@pytest.mark.parametrize(["first", "last"], [(None, None), (10, 10)])
def test_subset_raises_lazy(manifest_type, first, last):
    any_set = DummyManifest(manifest_type, begin_id=0, end_id=200)
    with pytest.raises(AssertionError):
        subset = any_set.subset(first=first, last=last)


@pytest.mark.parametrize(
    "manifest_type", [RecordingSet, SupervisionSet, FeatureSet, CutSet]
)
def test_map(manifest_type):

    expected = DummyManifest(manifest_type, begin_id=0, end_id=10)
    for item in expected:
        item.duration = 3.14

    def transform_fn(item):
        item.duration = 3.14
        return item

    data = DummyManifest(manifest_type, begin_id=0, end_id=10)
    eager_result = data.map(transform_fn)
    assert list(eager_result) == list(expected)

    with as_lazy(data) as lazy_data:
        lazy_result = lazy_data.map(transform_fn)
        assert list(lazy_result) == list(expected)


@pytest.mark.parametrize(
    "manifest_type", [RecordingSet, SupervisionSet, FeatureSet, CutSet]
)
def test_filter(manifest_type):

    expected = DummyManifest(manifest_type, begin_id=0, end_id=5)
    for idx, item in enumerate(expected):
        item.duration = idx

    def predicate(item):
        return item.duration < 5

    data = DummyManifest(manifest_type, begin_id=0, end_id=10)
    for idx, item in enumerate(data):
        item.duration = idx

    eager_result = data.filter(predicate)
    assert list(eager_result) == list(expected)

    with as_lazy(data) as lazy_data:
        lazy_result = lazy_data.filter(predicate)
        with pytest.raises(TypeError):
            len(lazy_result)
        assert list(lazy_result) == list(expected)


@pytest.mark.parametrize(
    "manifest_type", [RecordingSet, SupervisionSet, FeatureSet, CutSet]
)
@pytest.mark.parametrize("preserve_id", [True, False])
def test_repeat(manifest_type, preserve_id):
    data = DummyManifest(manifest_type, begin_id=0, end_id=10)

    expected = data + data

    eager_result = data.repeat(times=2, preserve_id=preserve_id)
    if preserve_id or manifest_type == FeatureSet:
        assert list(eager_result) == list(expected)
    else:
        items = list(eager_result)
        ref_items = list(expected)
        assert len(items) == len(ref_items)
        for i, refi in zip(items, ref_items):
            assert i.id.endswith("_repeat0") or i.id.endswith("_repeat1")
            i_modi = fastcopy(i, id=refi.id)
            assert i_modi == refi

    with as_lazy(data) as lazy_data:
        lazy_result = lazy_data.repeat(times=2, preserve_id=preserve_id)
        if preserve_id or manifest_type == FeatureSet:
            assert list(lazy_result) == list(expected)
        else:
            items = list(lazy_result)
            ref_items = list(expected)
            assert len(items) == len(ref_items)
            for i, refi in zip(items, ref_items):
                assert i.id.endswith("_repeat0") or i.id.endswith("_repeat1")
                i_modi = fastcopy(i, id=refi.id)
                assert i_modi == refi


@pytest.mark.parametrize(
    "manifest_type", [RecordingSet, SupervisionSet, FeatureSet, CutSet]
)
def test_repeat_infinite(manifest_type):
    data = DummyManifest(manifest_type, begin_id=0, end_id=10)

    # hard to test infinite iterables, iterate it 10x more times than the original size
    eager_result = data.repeat()
    for idx, item in enumerate(eager_result):
        if idx == 105:
            break
    assert idx == 105

    with as_lazy(data) as lazy_data:
        lazy_result = lazy_data.repeat()
        for idx, item in enumerate(lazy_result):
            if idx == 105:
                break
        assert idx == 105


def test_repeat_infinite_terminates_with_empty_iterable():
    data = []
    repeated_iter = LazyRepeater(data)
    result = list(repeated_iter)
    assert len(result) == 0


@pytest.mark.parametrize(
    "manifest_type", [RecordingSet, SupervisionSet, FeatureSet, CutSet]
)
def test_to_eager(manifest_type):
    data = DummyManifest(manifest_type, begin_id=0, end_id=10)

    with as_lazy(data) as lazy_data:
        eager_data = lazy_data.to_eager()
        assert isinstance(eager_data.data, type(data.data))
        assert eager_data == data
        assert list(eager_data) == list(data)


@pytest.mark.parametrize(
    "manifest_type",
    [
        RecordingSet,
        SupervisionSet,
        pytest.param(
            FeatureSet,
            marks=pytest.mark.xfail(reason="FeatureSet does not support shuffling."),
        ),
        CutSet,
    ],
)
def test_shuffle(manifest_type):
    data = DummyManifest(manifest_type, begin_id=0, end_id=4)
    for idx, item in enumerate(data):
        item.duration = idx

    expected_durations = [2, 1, 3, 0]

    rng = random.Random(42)

    eager_result = data.shuffle(rng=rng)
    assert [item.duration for item in eager_result] == list(expected_durations)

    with as_lazy(data) as lazy_data:
        lazy_result = lazy_data.shuffle(rng=rng)
        assert [item.duration for item in lazy_result] == list(expected_durations)


def test_composable_operations():
    expected_durations = [0, 2, 4, 6, 8, 0, 2, 4, 6, 8]

    data = DummyManifest(CutSet, begin_id=0, end_id=10)
    for idx, cut in enumerate(data):
        cut.duration = idx

    def less_than_5s(item):
        return item.duration < 5

    def double_duration(item):
        return fastcopy(item, duration=item.duration * 2)

    eager_result = data.repeat(2).filter(less_than_5s).map(double_duration)
    assert [c.duration for c in eager_result] == expected_durations

    with as_lazy(data) as lazy_data:
        lazy_result = lazy_data.repeat(2).filter(less_than_5s).map(double_duration)
        assert [item.duration for item in lazy_result] == list(expected_durations)


def _get_ids(cuts):
    return [cut.id for cut in cuts]


@pytest.mark.xfail(
    not is_module_available("dill"),
    reason="This test will fail when 'dill' module is not installed as it won't be able to pickle a lambda.",
    raises=AttributeError,
)
def test_dillable(with_dill_enabled):
    cuts = DummyManifest(CutSet, begin_id=0, end_id=2)
    with as_lazy(cuts) as lazy_cuts:
        lazy_cuts = lazy_cuts.map(lambda c: fastcopy(c, id=c.id + "-random-suffix"))
        with ProcessPoolExecutor(1) as ex:
            # Moves the cutset which has a lambda stored somewhere to another process,
            # iterates it there, and gets results back to the main process.
            # Should work with dill, shouldn't work with just pickle.
            ids = list(ex.map(_get_ids, [lazy_cuts]))

        assert ids[0] == [
            "dummy-mono-cut-0000-random-suffix",
            "dummy-mono-cut-0001-random-suffix",
        ]


def test_lazy_jsonl_iterator_caches_len():
    cuts = DummyManifest(CutSet, begin_id=0, end_id=200)
    expected_len = 200
    with as_lazy(cuts) as cuts_lazy:
        path = cuts_lazy.data.path
        print(path)
        it = LazyJsonlIterator(path)
        assert it._len is None
        for _ in it:
            pass
        assert it._len is not None
        assert it._len == expected_len
        assert len(it) == expected_len


def test_lazy_txt_iterator(tmp_path: Path):
    txt = tmp_path / "test.txt"
    txt.write_text("a\nb\nc\n")

    it = LazyTxtIterator(txt)

    # Supports len
    assert len(it) == 3

    # Can be iterated, strips newlines
    texts = [t for t in it]
    assert texts == [TextExample("a"), TextExample("b"), TextExample("c")]

    # Can be iterated again
    texts = [t for t in it]
    assert texts == [TextExample("a"), TextExample("b"), TextExample("c")]


def test_lazy_txt_iterator_raw_text(tmp_path: Path):
    txt = tmp_path / "test.txt"
    txt.write_text("a\nb\nc\n")

    it = LazyTxtIterator(txt, as_text_example=False)

    # Supports len
    assert len(it) == 3

    # Can be iterated, strips newlines
    texts = [t for t in it]
    assert texts == ["a", "b", "c"]

    # Can be iterated again
    texts = [t for t in it]
    assert texts == ["a", "b", "c"]
