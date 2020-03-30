# Guidelines On Messaging With AMQP

## Introduction
Before diving into the details of messaging with AMQP, we will consider some basic concepts you should consider.

## Contracts
A contract defines the message payload, and is the single point of truth on what type of payload to expect in the message. 
- [JSON schema](https://json-schema.org/) is a great tool to describe contracts.
- [Quicktype](https://app.quicktype.io/) is an online JSON schema renderer, targeting multiple frameworks such as Python, C#, Typescript and Java.

## Queues
A queue is the temporary storage of a message. All queues should be unique to every consumer context.

## Exchanges
An exchange is the message switch on the message broker. It routes incoming messages to subscribing queues based on message topics.

### Direct Exchanges
A direct exchange matches the whole topic with subscribing queues. Thus it is used to send a message with the `command` pattern to a single receiver, as a `one-to-one` exchange.

The default `direct exchange` used by PikaBus is named:
- `PikaBusDirect`

### Topic Exchanges
A topic exchange matches parts or more of the topic with subscribing queues. Thus it is used to publish a message with the `event` pattern to potentially many receiver, as a `one-to-many` exchange.

The default `topic exchange` used by PikaBus is named:
- `PikaBusTopic`

## Message Headers
All messages comes with headers giving some basic information about the message. PikaBus have defined a standard set of headers to enable different service implementations to comply on a common set of headers. The default `PikaBus` prefix is possible to change as preferred.

| Header Key                       | Header Value Type                 | Description                                                                                                           |
|----------------------------------|-----------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| PikaBus.MessageId                | Guid                              | Unique message id.                                                                                                    |
| PikaBus.CorrelationId            | Guid                              | Unique message correlation id.                                                                                        |
| PikaBus.ReplyToAddress           | String                            | Which address/queue to send replies.                                                                                  |
| PikaBus.OriginatingAddress       | String                            | Originating address/queue.                                                                                            |
| PikaBus.ContentType              | String                            | Content type, commonly `application/json`.                                                                            |
| PikaBus.ContentEncoding          | String                            | Content encoding, commonly `utf-8`.                                                                                   |
| PikaBus.MessageType              | String                            | Optional contract namespace of message type, commonly `<CONTRACT_NAMESPACE>.<CONTRACT_TYPE>`.                         |
| PikaBus.Intent                   | String                            | Message intent - `command` or `event`.                                                                                |
| PikaBus.TimeSent                 | String                            | UTC timestamp at what time the message was sent, commonly `07/22/2019 11:40:19` - (`month/day/year hour:min:sec`).    |
| PikaBus.ErrorDetails             | String                            | Error details attached in case of an exception.                                                                       |
| PikaBus.SourceQueue              | String                            | Source queue of a message that has been forwarded to an error queue after it has failed.                              |


## Events & Commands
With implementing a messaging service with PikaBus you will encounter the option to `Publish` or `Send` a message. Wether to choose either one follows a few basic principles.
In short, a message shall only have one logical owner and usage of the `Command` or `Event` principle follows the message ownership.

| Command                                           | Event                                                     |
|---------------------------------------------------|-----------------------------------------------------------|
| Used to make a request to perform an action.      | Used to communicate that an action has been performed.    |
| Shall be sent to the logical owner.               | Shall be published by the logical owner.                  |
| Cannot be published.                              | Cannot be sent.                                           |
| Cannot be subscribed to or unsubscribed from.     | Can be subscribed to and unsubscribed from.               |

- Table reference: https://docs.particular.net/nservicebus/messaging/messages-events-commands

### Events
A `published` message is an `event` notified by the owner of the message to the public to communicate that an action has been performed. Keep in mind ownership of the message contract, thus the owner will be the event notifier and will have all rights reserved for publishing that message. Any subsribers to the event will subscribe on the topic of the event.

### Topics

A topic is the event routing key used to `publish` a message, and must be unique across all services.
The topic must be explicitly defined for every contract.

### Commands
A `sent` message is a `command` sent directly to a recipient of a message endpoint to request an action. In this case, the message is owned by the consumer performing the action requested. With using [RabbitMq](https://www.rabbitmq.com/) as the message broker, the recipient address will be the queue name owned by the consumer.

### Message Endpoints

A message endpoint is an explicit routing of a message `sent` to a recipient.

## Event Types
There are mainly two types of events you should consider, notification and integration messages.

| Notification Events                                               | Integration Events                                        |
|-------------------------------------------------------------------|-----------------------------------------------------------|
| Contains short and concise information about the event.                               | Contains as much information as possible about the event.    |
| Calls must be made back to the originator of the event to obtain more information.    | No more calls needs to be made since all information about the event follows the message.   |
| Should only be used in closely coupled contexts due to coupling.                      | Should be used between decoupled contexts to keep them decoupled.    |

### Notification Events
Notification events should be short and concise, with minimal information describing the action performed. Any subsribers will react on the event usually by performing a synchronous call back to the publisher of the event to obtain more information. 

| Pros          | Cons      |
|---------------------------------------------------------------------------------------|--------------------------------------------|
| Event payload are kept at a minimum, and data is solely stored at the originator. | Calls back to originator creates coupling, and you may end up with chatty services. |

### Integration Events
Integration events contains as much information as possible about the event to easily keep subscribers eventually consistent with the originator without coupling.

| Pros          | Cons      |
|---------------------------------------------------------------------------------------|--------------------------------------------|
| All information about the event is contained within the message. | Data is usually copied across services, and kept consistent following the eventually consistency principle. |


## Error Handling
Failed messages occur when a service fails processing the message after a given number of retries. 

It is adviced to be as fault-tolerant as possible, and only throw an exception to fail the message when no other option is available.

By default, `PikaBus` implements error handling by forwarding failed messages to a durable queue named `error` 
after 5 retry attemps with backoff policy between each attempt.