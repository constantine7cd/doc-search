import datetime
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Any

import bson
import hydra
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from omegaconf import OmegaConf
from starlette import status
from starlette.middleware.sessions import SessionMiddleware

from auth.auth import router as auth_router
from core.conversation import (get_chat_history, get_conversation_runnable,
                               serialize_conversation)
from core.db import AsyncMongoDB, init_mongo_db_instance
from core.retrievers.document_retriever import DocumentRetriever
from core.summarizers.solution_analyzer import SolutionAggregator
from core.utils_hydra import register_resolvers
from core.utils_stream import parse_stream_chunk

load_dotenv()


@dataclass
class GenerateConfig:
    error_message: str
    documents: dict[str, list[dict[str, Any]]]
    yield_prompt: bool
    links: dict[str, list[str]]


@dataclass
class FollowUpConfig:
    user_text: str
    query_id: str


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
    allow_methods=["POST", "GET"],
    allow_credentials=True,
)
SECRET_KEY = os.getenv("SECRET_KEY")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.include_router(auth_router)

register_resolvers()
conf = OmegaConf.load("conf/prod.yaml")

document_retriever: DocumentRetriever = hydra.utils.instantiate(conf.document_retriever)
solution_aggregator: SolutionAggregator = hydra.utils.instantiate(
    conf.solution_aggregator
)
conversation_llm = hydra.utils.instantiate(conf.conversation_llm)
db: AsyncMongoDB = init_mongo_db_instance(
    is_async=True, default_db="troubleshooting", default_collection="search_queries"
)


async def generate_request_handler(config: GenerateConfig):
    prompt = None
    llm_response = []
    async for chunk in solution_aggregator.generate_solution(
        config.error_message, config.documents, yield_prompt=config.yield_prompt
    ):
        if config.yield_prompt and prompt is None:
            prompt = chunk
        else:
            yield chunk
            llm_response.append(chunk)

    llm_response = "".join(llm_response)
    prompt = prompt or config.error_message

    conversation = serialize_conversation([prompt, llm_response])
    curr_time = datetime.now(UTC)
    data = {
        "user_id": None,
        "query_text": config.error_message,
        "links": config.links,
        "created_at": curr_time,
        "updated_at": curr_time,
        "conversation": conversation,
        "search_engine": "google",
    }
    db_response = await db.insert(data)
    query_id = str(db_response.inserted_id)

    if config.links["links_succeeded"]:
        links_str = ", ".join(
            [
                f"[{index + 1}]({link})"
                for index, link in enumerate(config.links["links_succeeded"])
            ]
        )
        yield ("\n\n" f" - **References:** ({links_str})")
    yield ("\n\n" f" - **QUERY ID:** {query_id}")


async def follow_up_request_handler(config: FollowUpConfig):
    conversation_runnable = get_conversation_runnable(
        conversation_llm, partial(get_chat_history, mongo_client=db)
    )
    async for chunk in conversation_runnable.astream(
        {"question": config.user_text},
        config={"configurable": {"session_id": config.query_id}},
    ):
        yield parse_stream_chunk(chunk)


@app.get("/")
async def read_root():
    return {"Hello": "World"}


@app.post("/generate_solution")
async def generate_solution(error_message: str):
    documents, links = await document_retriever.retrieve_documents(error_message)
    config = GenerateConfig(
        error_message=error_message,
        documents=documents,
        yield_prompt=True,
        links=links,
    )
    return StreamingResponse(
        generate_request_handler(config),
        media_type="text/plain",
    )


@app.post("/follow_up")
async def follow_up(user_text: str, query_id: str):
    if not bson.ObjectId.is_valid(query_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Query ID is not valid."},
        )
    if await db.get_by_id(query_id) is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "Query ID not found."},
        )
    config = FollowUpConfig(user_text=user_text, query_id=query_id)
    return StreamingResponse(
        follow_up_request_handler(config),
        media_type="text/plain",
    )


@app.post("/add_reaction/{reaction}")
async def add_reaction(reaction: str, query_id: str):
    if reaction not in ["like", "dislike"]:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Reaction is not valid."},
        )
    if not bson.ObjectId.is_valid(query_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Query ID is not valid."},
        )
    if await db.get_by_id(query_id) is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "Query ID not found."},
        )
    data = await db.get({"search_query_id": query_id}, collection="reactions")
    if data is not None and data["reaction"] == reaction:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Reaction already added."},
        )
    update_data = {
        "reaction": reaction,
        "user_id": None,
        "created_at": datetime.now(UTC),
    }
    await db.update(
        {"search_query_id": query_id},
        {"$set": update_data},
        collection="reactions",
        upsert=True,
    )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Reaction added successfully."},
    )


@app.post("/remove_reaction/{reaction}")
async def remove_reaction(reaction: str, query_id: str):
    if reaction not in ["like", "dislike"]:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Reaction is not valid."},
        )
    if not bson.ObjectId.is_valid(query_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Query ID is not valid."},
        )
    data = await db.get({"search_query_id": query_id}, collection="reactions")
    if data is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": "Reaction not found."},
        )
    if data["reaction"] != reaction:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Reaction does not match."},
        )
    await db.delete({"search_query_id": query_id}, collection="reactions")
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "Reaction removed successfully."},
    )


@app.get("/reaction")
async def get_reaction(query_id: str):
    if not bson.ObjectId.is_valid(query_id):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"error": "Query ID is not valid."},
        )
    data = await db.get({"search_query_id": query_id}, collection="reactions")
    if data is None:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"reaction": None},
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"reaction": data["reaction"]},
    )
