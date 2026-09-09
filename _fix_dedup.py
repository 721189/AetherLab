"""Fix the REAL create_many to use ON CONFLICT DO NOTHING."""
import pathlib

path = pathlib.Path("app/services/environmental/ingestion.py")
text = path.read_text(encoding="utf-8")

old = '''    def create_many(
        self, observations: List[EnvironmentalObservation]
    ) -> List[EnvironmentalObservationRecord]:
        """Insert a batch atomically; idempotently skip existing observations.

        New rows for this batch are added to the session and committed exactly
        once. If anything fails, the entire batch is rolled back (no partial
        writes). Already-persisted hashes are excluded first, so a retried
        batch never inserts duplicates and never fails on a UNIQUE violation.
        """
        records: List[EnvironmentalObservationRecord] = []
        for obs in observations:
            rec = self._to_record(obs)
            if self._hash_exists(rec.observation_hash):
                continue  # already collected — idempotent skip
            self.db.add(rec)
            records.append(rec)

        if not records:
            return []

        try:
            self.db.commit()
        except Exception:
            self.db.rollback()  # atomic: no partial batch
            raise
        return records'''

new = '''    def create_many(
        self, observations: List[EnvironmentalObservation]
    ) -> List[EnvironmentalObservationRecord]:
        """Insert a batch atomically; idempotently skip existing observations.

        Dedup is **database-native** (``ON CONFLICT DO NOTHING``), not
        application-level check-then-insert. This makes ingestion safe under
        concurrent Celery workers: two tasks that fetch the same scene cannot
        both insert it — the UNIQUE index on ``observation_hash`` guarantees
        idempotency at the database level, eliminating the race condition that
        a read-then-write pattern would have.

        If anything fails, the entire batch is rolled back (no partial writes).
        """
        if not observations:
            return []

        table = EnvironmentalObservationRecord.__table__
        row_dicts = []
        for obs in observations:
            rec = self._to_record(obs)
            row_dicts.append(
                {
                    "source": rec.source,
                    "dataset": rec.dataset,
                    "product": rec.product,
                    "processing_level": rec.processing_level,
                    "resolution": rec.resolution,
                    "variable": rec.variable,
                    "value": rec.value,
                    "unit": rec.unit,
                    "latitude": rec.latitude,
                    "longitude": rec.longitude,
                    "location_name": rec.location_name,
                    "observed_at": rec.observed_at,
                    "acquisition_time": rec.acquisition_time,
                    "retrieved_at": rec.retrieved_at,
                    "averaging_period": rec.averaging_period,
                    "quality": rec.quality,
                    "quality_score": rec.quality_score,
                    "data_completeness": rec.data_completeness,
                    "confidence": rec.confidence,
                    "uncertainty": rec.uncertainty,
                    "provenance": rec.provenance,
                    "quality_flags": rec.quality_flags,
                    "observation_hash": rec.observation_hash,
                }
            )

        try:
            # Database-native dedup: ON CONFLICT DO NOTHING makes the insert
            # idempotent even under concurrent workers. The UNIQUE index on
            # observation_hash guarantees no duplicate rows.
            stmt = insert(table).values(row_dicts)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["observation_hash"]
            )
            self.db.execute(stmt)
            self.db.commit()
            # Return the ORM rows that exist for the hashes we just inserted
            # (query-back gives proper records with DB-generated IDs).
            inserted = (
                self.db.query(EnvironmentalObservationRecord)
                .filter(
                    EnvironmentalObservationRecord.observation_hash.in_(
                        [rd["observation_hash"] for rd in row_dicts]
                    )
                )
                .all()
            )
            return inserted
        except Exception:
            self.db.rollback()  # atomic: no partial batch
            raise'''

if old not in text:
    raise SystemExit("ERROR: old text not found in file")

text = text.replace(old, new)

# Add the `insert` import
if "from sqlalchemy import insert" not in text:
    text = text.replace(
        "from sqlalchemy.orm import Session",
        "from sqlalchemy import insert\nfrom sqlalchemy.orm import Session",
    )

path.write_text(text, encoding="utf-8")
print("OK: create_many now uses ON CONFLICT DO NOTHING")
