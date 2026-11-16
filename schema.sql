-- Flanged joints database.
-- A line contains joints, a joint is made of components,
-- and each component is one item of the catalog.

-- One row per PCF file (one pipeline).
CREATE TABLE IF NOT EXISTS lines (
    reference        VARCHAR(50)  PRIMARY KEY,
    piping_spec      VARCHAR(50),
    nominal_class    INTEGER,
    bore_units       VARCHAR(10),
    coordinate_units VARCHAR(10),
    source_file      VARCHAR(255)
);

-- One row per item code (the MATERIALS section of a PCF file).
-- description is NULL when the file gives no description for the code.
CREATE TABLE IF NOT EXISTS items (
    item_code      VARCHAR(50)  PRIMARY KEY,
    description    VARCHAR(255),
    pressure_class INTEGER,
    facing         VARCHAR(5),
    CHECK (facing IN ('RF', 'FF', 'RTJ'))
);

-- One row per flanged joint. x, y, z is its reference position:
-- the point where flange A meets the gasket.
CREATE TABLE IF NOT EXISTS joints (
    id             INTEGER      PRIMARY KEY,
    line_reference VARCHAR(50)  NOT NULL,
    x              DOUBLE PRECISION,
    y              DOUBLE PRECISION,
    z              DOUBLE PRECISION,
    FOREIGN KEY (line_reference) REFERENCES lines (reference)
);

-- One row per physical part of a joint: flanges, gasket, bolt set.
-- skey is used by flanges; length and quantity by bolt sets.
-- x1..z1 and x2..z2 are the two end points of the part, as in the PCF file
-- (bolt sets have none).
CREATE TABLE IF NOT EXISTS joint_components (
    id             INTEGER      PRIMARY KEY,
    joint_id       INTEGER      NOT NULL,
    role           VARCHAR(10)  NOT NULL,
    component_type VARCHAR(20)  NOT NULL,
    item_code      VARCHAR(50),
    skey           VARCHAR(10),
    size           VARCHAR(10),
    length         DOUBLE PRECISION,
    quantity       INTEGER,
    x1             DOUBLE PRECISION,
    y1             DOUBLE PRECISION,
    z1             DOUBLE PRECISION,
    x2             DOUBLE PRECISION,
    y2             DOUBLE PRECISION,
    z2             DOUBLE PRECISION,
    FOREIGN KEY (joint_id) REFERENCES joints (id),
    FOREIGN KEY (item_code) REFERENCES items (item_code),
    UNIQUE (joint_id, role),
    CHECK (role IN ('FLANGE_A', 'FLANGE_B', 'GASKET', 'BOLTS')),
    CHECK (quantity > 0)
);

-- One row per finding of the checks.
CREATE TABLE IF NOT EXISTS issues (
    id       INTEGER      PRIMARY KEY,
    joint_id INTEGER      NOT NULL,
    code     VARCHAR(30)  NOT NULL,
    message  VARCHAR(255),
    FOREIGN KEY (joint_id) REFERENCES joints (id)
);
