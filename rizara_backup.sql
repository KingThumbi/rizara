--
-- PostgreSQL database dump
--

\restrict X18FeJmndp7nNcYLmRXUmDb1uT83yD44WZW8bJDbPq0o8vR4xIGaNV2gwQxdO87

-- Dumped from database version 16.11 (Ubuntu 16.11-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.11 (Ubuntu 16.11-0ubuntu0.24.04.1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: thumbi
--

-- *not* creating schema, since initdb creates it


ALTER SCHEMA public OWNER TO thumbi;

--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: thumbi
--

COMMENT ON SCHEMA public IS '';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: aggregation_batch; Type: TABLE; Schema: public; Owner: thumbi
--

CREATE TABLE public.aggregation_batch (
    id integer NOT NULL,
    site_name character varying(120) NOT NULL,
    date_received date,
    is_locked boolean,
    locked_at timestamp without time zone
);


ALTER TABLE public.aggregation_batch OWNER TO thumbi;

--
-- Name: aggregation_batch_id_seq; Type: SEQUENCE; Schema: public; Owner: thumbi
--

CREATE SEQUENCE public.aggregation_batch_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.aggregation_batch_id_seq OWNER TO thumbi;

--
-- Name: aggregation_batch_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: thumbi
--

ALTER SEQUENCE public.aggregation_batch_id_seq OWNED BY public.aggregation_batch.id;


--
-- Name: aggregation_goats; Type: TABLE; Schema: public; Owner: thumbi
--

CREATE TABLE public.aggregation_goats (
    goat_id uuid NOT NULL,
    aggregation_batch_id integer NOT NULL
);


ALTER TABLE public.aggregation_goats OWNER TO thumbi;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: thumbi
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO thumbi;

--
-- Name: farmer; Type: TABLE; Schema: public; Owner: thumbi
--

CREATE TABLE public.farmer (
    id integer NOT NULL,
    name character varying(120) NOT NULL,
    phone character varying(20) NOT NULL,
    onboarded_at timestamp without time zone,
    county character varying(100) NOT NULL,
    ward character varying(100) NOT NULL,
    village character varying(120),
    latitude double precision,
    longitude double precision,
    location_notes character varying(255)
);


ALTER TABLE public.farmer OWNER TO thumbi;

--
-- Name: farmer_id_seq; Type: SEQUENCE; Schema: public; Owner: thumbi
--

CREATE SEQUENCE public.farmer_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.farmer_id_seq OWNER TO thumbi;

--
-- Name: farmer_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: thumbi
--

ALTER SEQUENCE public.farmer_id_seq OWNED BY public.farmer.id;


--
-- Name: goat; Type: TABLE; Schema: public; Owner: thumbi
--

CREATE TABLE public.goat (
    id uuid NOT NULL,
    farmer_tag character varying(64) NOT NULL,
    rizara_id character varying(64) NOT NULL,
    sex character varying(10),
    breed character varying(50),
    estimated_dob date,
    status character varying(30) NOT NULL,
    farmer_id integer NOT NULL,
    created_at timestamp without time zone
);


ALTER TABLE public.goat OWNER TO thumbi;

--
-- Name: processing_batch; Type: TABLE; Schema: public; Owner: thumbi
--

CREATE TABLE public.processing_batch (
    id integer NOT NULL,
    facility character varying(120) NOT NULL,
    slaughter_date date,
    halal_cert_ref character varying(120),
    is_locked boolean,
    locked_at timestamp without time zone
);


ALTER TABLE public.processing_batch OWNER TO thumbi;

--
-- Name: processing_batch_id_seq; Type: SEQUENCE; Schema: public; Owner: thumbi
--

CREATE SEQUENCE public.processing_batch_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.processing_batch_id_seq OWNER TO thumbi;

--
-- Name: processing_batch_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: thumbi
--

ALTER SEQUENCE public.processing_batch_id_seq OWNED BY public.processing_batch.id;


--
-- Name: processing_goats; Type: TABLE; Schema: public; Owner: thumbi
--

CREATE TABLE public.processing_goats (
    goat_id uuid NOT NULL,
    processing_batch_id integer NOT NULL
);


ALTER TABLE public.processing_goats OWNER TO thumbi;

--
-- Name: traceability_record; Type: TABLE; Schema: public; Owner: thumbi
--

CREATE TABLE public.traceability_record (
    id integer NOT NULL,
    goat_id uuid NOT NULL,
    qr_code_data text NOT NULL,
    public_url character varying(255) NOT NULL,
    created_at timestamp without time zone
);


ALTER TABLE public.traceability_record OWNER TO thumbi;

--
-- Name: traceability_record_id_seq; Type: SEQUENCE; Schema: public; Owner: thumbi
--

CREATE SEQUENCE public.traceability_record_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.traceability_record_id_seq OWNER TO thumbi;

--
-- Name: traceability_record_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: thumbi
--

ALTER SEQUENCE public.traceability_record_id_seq OWNED BY public.traceability_record.id;


--
-- Name: user; Type: TABLE; Schema: public; Owner: thumbi
--

CREATE TABLE public."user" (
    id integer NOT NULL,
    email character varying(120) NOT NULL,
    password_hash character varying(255) NOT NULL,
    is_admin boolean,
    created_at timestamp without time zone
);


ALTER TABLE public."user" OWNER TO thumbi;

--
-- Name: user_id_seq; Type: SEQUENCE; Schema: public; Owner: thumbi
--

CREATE SEQUENCE public.user_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_id_seq OWNER TO thumbi;

--
-- Name: user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: thumbi
--

ALTER SEQUENCE public.user_id_seq OWNED BY public."user".id;


--
-- Name: aggregation_batch id; Type: DEFAULT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.aggregation_batch ALTER COLUMN id SET DEFAULT nextval('public.aggregation_batch_id_seq'::regclass);


--
-- Name: farmer id; Type: DEFAULT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.farmer ALTER COLUMN id SET DEFAULT nextval('public.farmer_id_seq'::regclass);


--
-- Name: processing_batch id; Type: DEFAULT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.processing_batch ALTER COLUMN id SET DEFAULT nextval('public.processing_batch_id_seq'::regclass);


--
-- Name: traceability_record id; Type: DEFAULT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.traceability_record ALTER COLUMN id SET DEFAULT nextval('public.traceability_record_id_seq'::regclass);


--
-- Name: user id; Type: DEFAULT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public."user" ALTER COLUMN id SET DEFAULT nextval('public.user_id_seq'::regclass);


--
-- Data for Name: aggregation_batch; Type: TABLE DATA; Schema: public; Owner: thumbi
--

COPY public.aggregation_batch (id, site_name, date_received, is_locked, locked_at) FROM stdin;
1	Kaewa	2026-01-07	f	\N
2	Kaewa	2026-01-07	f	\N
3	Kaewa	2026-01-08	f	\N
4	Kaewa	2026-01-09	f	\N
\.


--
-- Data for Name: aggregation_goats; Type: TABLE DATA; Schema: public; Owner: thumbi
--

COPY public.aggregation_goats (goat_id, aggregation_batch_id) FROM stdin;
b7ed80a4-5d1a-4464-ab7a-7a299336fcdf	1
e9f21ba6-a625-4f04-b814-8cfbbe190529	2
79862a13-e6d7-423f-9f74-5da54aa91601	2
6875c0eb-c298-43f9-aa21-b0419c91ceb7	3
8cec16f5-98ed-4c0b-b014-a7aceb80d6ba	4
b49930e6-df80-4b19-aec7-70b68ad0412c	4
\.


--
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: thumbi
--

COPY public.alembic_version (version_num) FROM stdin;
c8da5b6973c7
\.


--
-- Data for Name: farmer; Type: TABLE DATA; Schema: public; Owner: thumbi
--

COPY public.farmer (id, name, phone, onboarded_at, county, ward, village, latitude, longitude, location_notes) FROM stdin;
1	John Doe	0700123123	2026-01-07 18:45:05.953455	Machakos	Kaewa	\N	\N	\N	\N
2	Sue Joe	0728885783	2026-01-07 20:08:34.734152	Kitui	Kathiani	\N	\N	\N	\N
3	Kim Joe	0700123456	2026-01-07 20:38:18.215517	Kiambu	Komothai	\N	\N	\N	\N
4	Samson Joe	0722123456	2026-01-08 19:41:26.256038	Kitui	Kitui Central	Kyangwithya East	-1.339427551913669	38.05035550488825	Kwanzou Primary School
5	IAn Muendo Nzila	0712345678	2026-01-09 10:22:01.529017	Kitui	Kisasi	Mwaani Shopping Centre	-1.5035746757530448	38.03185166539075	Near Kisasi Polytechnic
\.


--
-- Data for Name: goat; Type: TABLE DATA; Schema: public; Owner: thumbi
--

COPY public.goat (id, farmer_tag, rizara_id, sex, breed, estimated_dob, status, farmer_id, created_at) FROM stdin;
6875c0eb-c298-43f9-aa21-b0419c91ceb7	Kim Joe	RZ-GT-2026-3-002	Male	Boer	2025-01-31	processed	3	2026-01-08 19:30:28.498557
79862a13-e6d7-423f-9f74-5da54aa91601	Sue Joe	RZ-GT-2026-2-001	Male	Galla	2024-11-29	processed	2	2026-01-08 17:24:59.920473
b7ed80a4-5d1a-4464-ab7a-7a299336fcdf	Kim Joe	RZ-GT-2026-3-001	Male	Galla	2026-01-01	processed	3	2026-01-07 20:38:45.008227
e9f21ba6-a625-4f04-b814-8cfbbe190529	John Doe	RZ-GT-2026-1-001	Female	Boer	2024-12-10	processed	1	2026-01-08 17:23:38.509661
56992867-aa3b-4d55-80c6-c53731c8c32c	IAn Muendo Nzila	RZ-GT-2026-5-001	Male	Boer	2023-08-02	on_farm	5	2026-01-09 10:23:21.116275
6517ed4b-112b-4f5c-bc11-5fc6e47c783e	IAn Muendo Nzila	RZ-GT-2026-5-002	Female	Red Kalahari	2024-05-01	on_farm	5	2026-01-09 10:24:10.909757
9da4f0c7-dc2a-4f63-bb33-4ba359a9cdbd	IAn Muendo Nzila	RZ-GT-2026-5-003	Female	Red Kalahari	2028-02-28	on_farm	5	2026-01-09 10:24:47.852402
cd95842a-ac98-4646-9275-69341539a41d	IAn Muendo Nzila	RZ-GT-2026-5-004	Female	Red Kalahari	2025-06-01	on_farm	5	2026-01-09 10:25:18.63093
4c4394ad-7778-4bf1-8e76-2f2fedbdc086	IAn Muendo Nzila	RZ-GT-2026-5-005	Female	Red Kalahari	2025-07-24	on_farm	5	2026-01-09 10:25:44.425851
b49930e6-df80-4b19-aec7-70b68ad0412c	Samson Joe	RZ-GT-2026-4-001	Male	Kalahari Red	2025-03-01	aggregated	4	2026-01-08 19:43:58.87509
8cec16f5-98ed-4c0b-b014-a7aceb80d6ba	John Doe	RZ-GT-2026-1-002	Male	Galla	2025-01-31	processed	1	2026-01-08 19:34:53.146633
\.


--
-- Data for Name: processing_batch; Type: TABLE DATA; Schema: public; Owner: thumbi
--

COPY public.processing_batch (id, facility, slaughter_date, halal_cert_ref, is_locked, locked_at) FROM stdin;
1	Juja International Abattoir	2026-01-09	123654	f	\N
2	Juja International Abattoir	2026-01-09	13245	f	\N
\.


--
-- Data for Name: processing_goats; Type: TABLE DATA; Schema: public; Owner: thumbi
--

COPY public.processing_goats (goat_id, processing_batch_id) FROM stdin;
b7ed80a4-5d1a-4464-ab7a-7a299336fcdf	1
6875c0eb-c298-43f9-aa21-b0419c91ceb7	1
79862a13-e6d7-423f-9f74-5da54aa91601	1
e9f21ba6-a625-4f04-b814-8cfbbe190529	1
8cec16f5-98ed-4c0b-b014-a7aceb80d6ba	2
\.


--
-- Data for Name: traceability_record; Type: TABLE DATA; Schema: public; Owner: thumbi
--

COPY public.traceability_record (id, goat_id, qr_code_data, public_url, created_at) FROM stdin;
\.


--
-- Data for Name: user; Type: TABLE DATA; Schema: public; Owner: thumbi
--

COPY public."user" (id, email, password_hash, is_admin, created_at) FROM stdin;
1	admin@rizara.com	pbkdf2:sha256:1000000$VciGJxjBiXOix1DA$f02964f219c9a881419b5a0a5c931270310a096fdef7eb3c41737dc0960ae509	t	2026-01-07 12:27:43.025822
\.


--
-- Name: aggregation_batch_id_seq; Type: SEQUENCE SET; Schema: public; Owner: thumbi
--

SELECT pg_catalog.setval('public.aggregation_batch_id_seq', 4, true);


--
-- Name: farmer_id_seq; Type: SEQUENCE SET; Schema: public; Owner: thumbi
--

SELECT pg_catalog.setval('public.farmer_id_seq', 5, true);


--
-- Name: processing_batch_id_seq; Type: SEQUENCE SET; Schema: public; Owner: thumbi
--

SELECT pg_catalog.setval('public.processing_batch_id_seq', 2, true);


--
-- Name: traceability_record_id_seq; Type: SEQUENCE SET; Schema: public; Owner: thumbi
--

SELECT pg_catalog.setval('public.traceability_record_id_seq', 1, false);


--
-- Name: user_id_seq; Type: SEQUENCE SET; Schema: public; Owner: thumbi
--

SELECT pg_catalog.setval('public.user_id_seq', 1, true);


--
-- Name: aggregation_batch aggregation_batch_pkey; Type: CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.aggregation_batch
    ADD CONSTRAINT aggregation_batch_pkey PRIMARY KEY (id);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: farmer farmer_phone_key; Type: CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.farmer
    ADD CONSTRAINT farmer_phone_key UNIQUE (phone);


--
-- Name: farmer farmer_pkey; Type: CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.farmer
    ADD CONSTRAINT farmer_pkey PRIMARY KEY (id);


--
-- Name: goat goat_pkey; Type: CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.goat
    ADD CONSTRAINT goat_pkey PRIMARY KEY (id);


--
-- Name: goat goat_rizara_id_key; Type: CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.goat
    ADD CONSTRAINT goat_rizara_id_key UNIQUE (rizara_id);


--
-- Name: processing_batch processing_batch_pkey; Type: CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.processing_batch
    ADD CONSTRAINT processing_batch_pkey PRIMARY KEY (id);


--
-- Name: traceability_record traceability_record_pkey; Type: CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.traceability_record
    ADD CONSTRAINT traceability_record_pkey PRIMARY KEY (id);


--
-- Name: user user_email_key; Type: CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public."user"
    ADD CONSTRAINT user_email_key UNIQUE (email);


--
-- Name: user user_pkey; Type: CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public."user"
    ADD CONSTRAINT user_pkey PRIMARY KEY (id);


--
-- Name: aggregation_goats aggregation_goats_aggregation_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.aggregation_goats
    ADD CONSTRAINT aggregation_goats_aggregation_batch_id_fkey FOREIGN KEY (aggregation_batch_id) REFERENCES public.aggregation_batch(id);


--
-- Name: aggregation_goats aggregation_goats_goat_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.aggregation_goats
    ADD CONSTRAINT aggregation_goats_goat_id_fkey FOREIGN KEY (goat_id) REFERENCES public.goat(id);


--
-- Name: goat goat_farmer_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.goat
    ADD CONSTRAINT goat_farmer_id_fkey FOREIGN KEY (farmer_id) REFERENCES public.farmer(id);


--
-- Name: processing_goats processing_goats_goat_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.processing_goats
    ADD CONSTRAINT processing_goats_goat_id_fkey FOREIGN KEY (goat_id) REFERENCES public.goat(id);


--
-- Name: processing_goats processing_goats_processing_batch_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.processing_goats
    ADD CONSTRAINT processing_goats_processing_batch_id_fkey FOREIGN KEY (processing_batch_id) REFERENCES public.processing_batch(id);


--
-- Name: traceability_record traceability_record_goat_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: thumbi
--

ALTER TABLE ONLY public.traceability_record
    ADD CONSTRAINT traceability_record_goat_id_fkey FOREIGN KEY (goat_id) REFERENCES public.goat(id);


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: thumbi
--

REVOKE USAGE ON SCHEMA public FROM PUBLIC;


--
-- PostgreSQL database dump complete
--

\unrestrict X18FeJmndp7nNcYLmRXUmDb1uT83yD44WZW8bJDbPq0o8vR4xIGaNV2gwQxdO87

