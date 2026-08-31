# Changelog

## [0.3.0](https://github.com/rohangawhade/policy-chatbot/compare/v0.2.0...v0.3.0) (2026-08-31)


### Features

* **chat:** expose retrieved contexts in chat responses; scaffold eval tooling ([#75](https://github.com/rohangawhade/policy-chatbot/issues/75)) ([e0365f0](https://github.com/rohangawhade/policy-chatbot/commit/e0365f0f285cc13bf3cf70e7d6fa8d712dfa65eb))
* **eval:** add RAGAS evaluation runner (Step 12.2) ([#81](https://github.com/rohangawhade/policy-chatbot/issues/81)) ([ccd02f7](https://github.com/rohangawhade/policy-chatbot/commit/ccd02f7ef220908245a431e7028e169647930e37))
* **llm:** wire real Pinecone embeddings via inference API ([#73](https://github.com/rohangawhade/policy-chatbot/issues/73)) ([3197ce2](https://github.com/rohangawhade/policy-chatbot/commit/3197ce2c58f36dff294ff4c36b200d1e39426e31))
* **scripts:** generate synthetic employer policy docs via LLM (Step 11.2) ([#71](https://github.com/rohangawhade/policy-chatbot/issues/71)) ([890e3f4](https://github.com/rohangawhade/policy-chatbot/commit/890e3f4b7995e9aa7b9020e03d653fb7d000159a))


### Bug Fixes

* **eval:** remove cross-tenant assumptions from golden dataset ([#74](https://github.com/rohangawhade/policy-chatbot/issues/74)) ([98015b2](https://github.com/rohangawhade/policy-chatbot/commit/98015b21e257b6fc0312a70cea2f4095adc7b6ef))
* **ingestion:** wire Pinecone embeddings into the ingestion task; support .docx/.xlsx/.xml uploads in seed_data.py ([#76](https://github.com/rohangawhade/policy-chatbot/issues/76)) ([e5ee2c2](https://github.com/rohangawhade/policy-chatbot/commit/e5ee2c278862e8bfdebdbde91f11072ee958dcc7))
* **llm:** batch Pinecone embed() calls to stay under its 96-input limit ([#77](https://github.com/rohangawhade/policy-chatbot/issues/77)) ([3f23c28](https://github.com/rohangawhade/policy-chatbot/commit/3f23c286e34c5182a9c0b6c56305e9f905a179ac))
* **seed:** give each employer its own synthetic documents, not a shared round-robin pool ([#79](https://github.com/rohangawhade/policy-chatbot/issues/79)) ([c1bb744](https://github.com/rohangawhade/policy-chatbot/commit/c1bb7440282b5a2097f80ad79acb2231285bd757))
* **seed:** tag synthetic policy-summary uploads with their policy_type ([#80](https://github.com/rohangawhade/policy-chatbot/issues/80)) ([f053b78](https://github.com/rohangawhade/policy-chatbot/commit/f053b78bb9acd7709be6207bf2d6e48aa9dda044))
* **vector-store:** batch Pinecone upsert() to stay under its 4MB request limit ([#78](https://github.com/rohangawhade/policy-chatbot/issues/78)) ([3970c0a](https://github.com/rohangawhade/policy-chatbot/commit/3970c0a55d1fed930f33e5c8f67d7bdc37c282d0))


### Documentation

* confirm v0.2.0 release cut and close out Phase 14 ([#69](https://github.com/rohangawhade/policy-chatbot/issues/69)) ([ee13f07](https://github.com/rohangawhade/policy-chatbot/commit/ee13f07898e38337220fc5e38c361bc115e9e8cc))

## [0.2.0](https://github.com/rohangawhade/policy-chatbot/compare/v0.1.0...v0.2.0) (2026-08-27)


### Features

* **admin:** admin analytics routes + event-bus subscriber gap fix ([#45](https://github.com/rohangawhade/policy-chatbot/issues/45)) ([b5f9a33](https://github.com/rohangawhade/policy-chatbot/commit/b5f9a3353854435c61908cbb7a24f833a88886cb))
* **api:** add health and readiness probe endpoints ([#8](https://github.com/rohangawhade/policy-chatbot/issues/8)) ([19a410b](https://github.com/rohangawhade/policy-chatbot/commit/19a410b6840a3aa88fea680abb1b45ff996e3054))
* **auth:** add auth service with JWT access/refresh tokens ([#25](https://github.com/rohangawhade/policy-chatbot/issues/25)) ([fddbad6](https://github.com/rohangawhade/policy-chatbot/commit/fddbad62c780edd6e01fad2fcacdaf9afc464bc1))
* **auth:** add register, login, refresh, and me routes ([#40](https://github.com/rohangawhade/policy-chatbot/issues/40)) ([c1ffc0a](https://github.com/rohangawhade/policy-chatbot/commit/c1ffc0abaefaa8f89208abb4de3dec254fcd8882))
* **backend:** download real government benefits PDFs ([#56](https://github.com/rohangawhade/policy-chatbot/issues/56)) ([d631158](https://github.com/rohangawhade/policy-chatbot/commit/d6311587bb599fba15b3dad8b6036adc51fb7ffd))
* **backend:** global exception handling ([#60](https://github.com/rohangawhade/policy-chatbot/issues/60)) ([1a14dec](https://github.com/rohangawhade/policy-chatbot/commit/1a14decd1f1afde9a35fb9e3200c708c15896213))
* **backend:** seed script for demo employers/employees/policies ([#57](https://github.com/rohangawhade/policy-chatbot/issues/57)) ([e28c1bc](https://github.com/rohangawhade/policy-chatbot/commit/e28c1bc0c59a07c45c1c7994efe772d5672c7b4b))
* **backend:** structured logging with correlation IDs ([#59](https://github.com/rohangawhade/policy-chatbot/issues/59)) ([e00d577](https://github.com/rohangawhade/policy-chatbot/commit/e00d577f7d4b965d78961bc8eeb9aac6718ef1ec))
* **cache:** add Redis and in-memory cache adapters ([#18](https://github.com/rohangawhade/policy-chatbot/issues/18)) ([ff0e067](https://github.com/rohangawhade/policy-chatbot/commit/ff0e067107b4c5e4dbe612ff838672bc95852905))
* **cache:** invalidate cached queries by employer + policy type on document version change ([#36](https://github.com/rohangawhade/policy-chatbot/issues/36)) ([c003972](https://github.com/rohangawhade/policy-chatbot/commit/c0039720d228a2ac8e83368171837c84f110560e))
* **celery:** add queue routing, task retries, and dead-letter handling ([#37](https://github.com/rohangawhade/policy-chatbot/issues/37)) ([619cbad](https://github.com/rohangawhade/policy-chatbot/commit/619cbad9897ac9b0bd8f8ef76fe0f9a36eca5d1c))
* **chat:** add conversation CRUD and the RAG chat SSE endpoint ([#41](https://github.com/rohangawhade/policy-chatbot/issues/41)) ([65c0604](https://github.com/rohangawhade/policy-chatbot/commit/65c060461bfe0aa1f2917241da830ce8244649d9))
* **chunking:** add chunker pipeline orchestration ([#23](https://github.com/rohangawhade/policy-chatbot/issues/23)) ([dff5923](https://github.com/rohangawhade/policy-chatbot/commit/dff59230c5678a13d83145f672373c33507d67dd))
* **chunking:** add embedding-based semantic chunker ([#22](https://github.com/rohangawhade/policy-chatbot/issues/22)) ([ca6d6d5](https://github.com/rohangawhade/policy-chatbot/commit/ca6d6d5f8ed713398afd49072f58c22a7921ebad))
* **chunking:** add heading- and page-aware metadata extractor ([#21](https://github.com/rohangawhade/policy-chatbot/issues/21)) ([a3329a3](https://github.com/rohangawhade/policy-chatbot/commit/a3329a3fc9035b2b2da445b4ef80ca16214cd0d2))
* **config:** add typed environment-driven configuration ([#7](https://github.com/rohangawhade/policy-chatbot/issues/7)) ([0da81c6](https://github.com/rohangawhade/policy-chatbot/commit/0da81c674121c9501305fb57f73b2d6d7ff4b9b5))
* **document-processing:** add document processor adapters (Phase 3 complete) ([#20](https://github.com/rohangawhade/policy-chatbot/issues/20)) ([865d98e](https://github.com/rohangawhade/policy-chatbot/commit/865d98e7e9865dfd7e6f91a1a66227bab703366c))
* **document:** add version tracking to document uploads ([#34](https://github.com/rohangawhade/policy-chatbot/issues/34)) ([a5246a1](https://github.com/rohangawhade/policy-chatbot/commit/a5246a1a98b01913f71e39814d1508cf8eabeb22))
* **document:** purge old vectors and soft-delete chunks on version replacement ([#35](https://github.com/rohangawhade/policy-chatbot/issues/35)) ([e013982](https://github.com/rohangawhade/policy-chatbot/commit/e013982961e435b3ae427cc1d1e433ad73eee323))
* **documents:** add ingestion status endpoint and SSE stream ([#39](https://github.com/rohangawhade/policy-chatbot/issues/39)) ([1eb56bb](https://github.com/rohangawhade/policy-chatbot/commit/1eb56bb857ffdf04133e67a8ea9d0dbfe4c5e333))
* **documents:** add upload, list, and delete routes ([#42](https://github.com/rohangawhade/policy-chatbot/issues/42)) ([233714e](https://github.com/rohangawhade/policy-chatbot/commit/233714e264371662356121354189a58cda11676b))
* **domain:** add concrete domain event classes ([#11](https://github.com/rohangawhade/policy-chatbot/issues/11)) ([0471a2c](https://github.com/rohangawhade/policy-chatbot/commit/0471a2c09b4c2b557c961b37b326ae5c959a7ce5))
* **domain:** add pure domain models for core entities ([#9](https://github.com/rohangawhade/policy-chatbot/issues/9)) ([a14595a](https://github.com/rohangawhade/policy-chatbot/commit/a14595ae9903de4119e5d6588f65384f6d7d01c3))
* **embedding:** add embedding and indexing Celery task ([#24](https://github.com/rohangawhade/policy-chatbot/issues/24)) ([25ccbbe](https://github.com/rohangawhade/policy-chatbot/commit/25ccbbe040a34c59362e02bff9ab849e691f6a4f))
* **employees:** add employer, employee, and policy management routes ([#43](https://github.com/rohangawhade/policy-chatbot/issues/43)) ([bf7046b](https://github.com/rohangawhade/policy-chatbot/commit/bf7046beadc94a964f5e7f53c35f10587710b146))
* **events:** add in-memory event bus adapter ([#15](https://github.com/rohangawhade/policy-chatbot/issues/15)) ([c1507f9](https://github.com/rohangawhade/policy-chatbot/commit/c1507f9bc3064f2da1e4e1de61b7f94a53e2b682))
* **feedback:** add submit and analytics routes ([#44](https://github.com/rohangawhade/policy-chatbot/issues/44)) ([f60a1b7](https://github.com/rohangawhade/policy-chatbot/commit/f60a1b777176e9bf789f08549d10cdca6786ce0d))
* **frontend:** admin analytics and cost dashboard ([#52](https://github.com/rohangawhade/policy-chatbot/issues/52)) ([0cf0a8c](https://github.com/rohangawhade/policy-chatbot/commit/0cf0a8cc7a854895b35deab09974e7e917330d87))
* **frontend:** admin dashboard document & employer management ([#51](https://github.com/rohangawhade/policy-chatbot/issues/51)) ([f912d39](https://github.com/rohangawhade/policy-chatbot/commit/f912d39cafab5122801a9b1b57804f61e2efb0c1))
* **frontend:** admin operational health dashboard ([#54](https://github.com/rohangawhade/policy-chatbot/issues/54)) ([528911a](https://github.com/rohangawhade/policy-chatbot/commit/528911a78b6b48b3508aff5bf11e67406db1bbb0))
* **frontend:** admin quality-monitoring dashboard ([#53](https://github.com/rohangawhade/policy-chatbot/issues/53)) ([ee3143c](https://github.com/rohangawhade/policy-chatbot/commit/ee3143cff6ea5dd04000c6df892d1013c4570fb6))
* **frontend:** chat interface with SSE streaming ([#50](https://github.com/rohangawhade/policy-chatbot/issues/50)) ([858fb59](https://github.com/rohangawhade/policy-chatbot/commit/858fb593a43acb090ed6961a04590c8124b754f3))
* **frontend:** employer self-serve portal ([#55](https://github.com/rohangawhade/policy-chatbot/issues/55)) ([75fada7](https://github.com/rohangawhade/policy-chatbot/commit/75fada753667c63b4c0dc81faae8bf5bf3b18d2f))
* **frontend:** login page, auth API calls, and token refresh interceptor ([#48](https://github.com/rohangawhade/policy-chatbot/issues/48)) ([585f35f](https://github.com/rohangawhade/policy-chatbot/commit/585f35f55708a7f723f86878630f20dae41dd441))
* **guardrails:** add off-topic query classification ([#28](https://github.com/rohangawhade/policy-chatbot/issues/28)) ([8f88ecf](https://github.com/rohangawhade/policy-chatbot/commit/8f88ecf810a6da1a88040066cdd3dc08c615c656))
* **ingestion:** add the full document-ingestion Celery task ([#38](https://github.com/rohangawhade/policy-chatbot/issues/38)) ([fb12fe7](https://github.com/rohangawhade/policy-chatbot/commit/fb12fe7b18dbf25b6274967055a08969e43d88a9))
* **llm:** add LiteLLM and mock LLM adapters ([#16](https://github.com/rohangawhade/policy-chatbot/issues/16)) ([234c893](https://github.com/rohangawhade/policy-chatbot/commit/234c893abb0b3341ff2abe864c05019ff4a5f68b))
* **persistence:** add PostgreSQL repository adapters ([#19](https://github.com/rohangawhade/policy-chatbot/issues/19)) ([1c3f679](https://github.com/rohangawhade/policy-chatbot/commit/1c3f67973b709ec42c3be72b05c7f377e4315877))
* **persistence:** add PostgreSQL schema and Alembic migrations ([#6](https://github.com/rohangawhade/policy-chatbot/issues/6)) ([eeb901b](https://github.com/rohangawhade/policy-chatbot/commit/eeb901b2476c8054e7c9a67d9d337d3ee53d6094))
* **ports:** add abstract port interfaces ([#10](https://github.com/rohangawhade/policy-chatbot/issues/10)) ([40f1770](https://github.com/rohangawhade/policy-chatbot/commit/40f177019e66311162ba476584968780be189bf6))
* **rag:** add conversation memory ([#33](https://github.com/rohangawhade/policy-chatbot/issues/33)) ([5ed167f](https://github.com/rohangawhade/policy-chatbot/commit/5ed167f9e3b7e01f22fa9f5db3bc5754e0930e0f))
* **rag:** add prompt assembly to RAGService ([#31](https://github.com/rohangawhade/policy-chatbot/issues/31)) ([f529fb3](https://github.com/rohangawhade/policy-chatbot/commit/f529fb3795a82ea7ec8738965fb02fa5489be639))
* **rag:** add retrieval to RAGService ([#30](https://github.com/rohangawhade/policy-chatbot/issues/30)) ([069a5f7](https://github.com/rohangawhade/policy-chatbot/commit/069a5f71df0f0067a5b541436bd34059b01fffc0))
* **rag:** add streaming generation with cost/latency logging ([#32](https://github.com/rohangawhade/policy-chatbot/issues/32)) ([54a4eb3](https://github.com/rohangawhade/policy-chatbot/commit/54a4eb387d1572ddd456bca04f66919ecbf9c7bc))
* **router:** add query complexity router with model fallback ([#29](https://github.com/rohangawhade/policy-chatbot/issues/29)) ([46f998b](https://github.com/rohangawhade/policy-chatbot/commit/46f998babe829df2071add67aa8b17d3165eafb9))
* **vector-store:** add Pinecone adapter ([#17](https://github.com/rohangawhade/policy-chatbot/issues/17)) ([29c9489](https://github.com/rohangawhade/policy-chatbot/commit/29c9489b6530619f725d2bdc7235180548e358cd))


### Bug Fixes

* **backend:** wire CORS middleware into the FastAPI app ([#49](https://github.com/rohangawhade/policy-chatbot/issues/49)) ([8a69ce3](https://github.com/rohangawhade/policy-chatbot/commit/8a69ce3c44b3f3e6c393e67bde6203cdd30b1940))
* **ci:** fix release-please and set a sane initial version ([#13](https://github.com/rohangawhade/policy-chatbot/issues/13)) ([ca7ced7](https://github.com/rohangawhade/policy-chatbot/commit/ca7ced7a55ab9811925e3b51194ecede5ca0f9ac))


### Performance

* **backend:** jittered, configurable retry policy for external calls ([#62](https://github.com/rohangawhade/policy-chatbot/issues/62)) ([cbeb50b](https://github.com/rohangawhade/policy-chatbot/commit/cbeb50bbf3a000c3e4e617ff0af1e57a8739ba0c))


### Security

* **auth:** add auth middleware, role guards, and DI wiring ([#26](https://github.com/rohangawhade/policy-chatbot/issues/26)) ([66b4c16](https://github.com/rohangawhade/policy-chatbot/commit/66b4c16714167cef628fec63e34574112519c106))
* **backend:** per-user chat rate limiting ([#61](https://github.com/rohangawhade/policy-chatbot/issues/61)) ([2f9e495](https://github.com/rohangawhade/policy-chatbot/commit/2f9e4954047aa3af78efa2146c4e70b49f01b863))
* **tenant:** add tenant context middleware ([#27](https://github.com/rohangawhade/policy-chatbot/issues/27)) ([58fe112](https://github.com/rohangawhade/policy-chatbot/commit/58fe1123da0719927cb5c09852a2f87a251873ff))


### Documentation

* **backend:** OpenAPI tag groups, descriptions, and request examples ([#63](https://github.com/rohangawhade/policy-chatbot/issues/63)) ([a62c241](https://github.com/rohangawhade/policy-chatbot/commit/a62c2413b63ff8e26781254113d8d5f8d86432e0))
* confirm Step 9.7 health routes and close out Phase 9 ([#46](https://github.com/rohangawhade/policy-chatbot/issues/46)) ([d0dfda8](https://github.com/rohangawhade/policy-chatbot/commit/d0dfda8c0e2595493d672047622f44830812ae19))
* fix stale and broken content in README.md ([#65](https://github.com/rohangawhade/policy-chatbot/issues/65)) ([b346ca3](https://github.com/rohangawhade/policy-chatbot/commit/b346ca3a409a8a31836baa7f9a8233734cabfebe))
