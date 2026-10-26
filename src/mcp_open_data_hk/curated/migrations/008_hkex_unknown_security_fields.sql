-- Form 3B names an associated corporation without necessarily disclosing its
-- stock code. The listed issuer's class may also be absent. Preserve unknowns;
-- never substitute the issuer code or join a corporation by its name.
ALTER TABLE hkex.securities ALTER COLUMN stock_code DROP NOT NULL;
ALTER TABLE hkex.securities ALTER COLUMN share_class DROP NOT NULL;
