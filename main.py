from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI

def main():
    print("Hello, World!")
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    response = llm.invoke("Hello, how are you?")
    print(f"Response from LLM: {response}")

def aux():
    print
if __name__ == "__main__":
    main()