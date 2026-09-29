# Production

The production version of this application will need to do include the following:

- Public Facing Free system that allows any public user to view basic information about the project as well as chat about the project using Hybrid RAG.
- Protected Admin section that allows me (the admin) to upload/ingest new documents/projects as well as to modify and change project status, visibility, etc.

# Functionality

Since the current system is a CapStone "All In One" system, some key changes will need to be made.

- Authorization: we will need a way to restrict access to the Admin API surface.
- Project Chat Prompt Engineering: we will need to change the Project Chat prompt for several objectives
  - The ability to support either English (for me and potential employers) or German (for potential clients).
  - Remove any tools that support data mutation (i.e. tools added in the Capstone that won't work for the free version)
  - Supported Tools
    - Mapping
    - Geo Search (find Ashphalt Mischanlage nearest to construction site)
  - Query answering based on RAG shall include citations LIMITED in length to 3 sentences.
  - Query answering based on RAG shall include links and pointers to the original documents.
  - Regelwerk documents MAY not include Citations, they can ONLY include the Regelwerk identifier. In place of a citation, the user must be informed that they need to get that data themselves.
  - Additional controls to make sure hackers don't jailbreak the system.
- Enforce token usage limits, monthly cap and per user caps.
- Data Masking: add data masking for individuals. Companies are to be allowed.
- Add Impressum und Datenschutzerklarung
- Data Mutation UI and Functionality now goes to the Admin site, perhaps I create an Admin chat agent with the mutation tools exposed to that agent. Doesn't really matter, the important thing is that those functions are protected.

# Operational

- New routine for Zip Ingestion: this is partially also functional in that I will want to support new chunking (i.e. extracting info from Querschnitt diagrams). But most important is that the routine ingests as much data as it can to be credible without causing the errors it encounters now.
- Data Masking: all chunks shall be masked for personally identifiable information prior to any embedding or analysis by an LLM (unless that LLM is local).
- Schema Migrations: add the ability to migrate schema changes to live databases. i.e. Alembic.
- Deployment Hardening: modify docker-compose.yml to close off internal ports, making sure that only 80/443 ports are open.... I'd also want to make sure there is something like www.strassenbau-vergabe-assistant and admin.strassenbau-vergabe-assistant. This needs to be built in a way that I can simply run docker compose on an AWS instance or a GCP instance or an Azure Instance and all the necessary services, databases, etc. start up and run without any security weaknesses (errant open ports, etc.). We could also assume that an ALB and firewall are in front of the instance as well.
